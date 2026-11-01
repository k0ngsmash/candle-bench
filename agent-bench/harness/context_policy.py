"""Context-retention policies applied to an agent's message list before it reaches the engine.

This is the prompt-assembly layer for the application-level arms of the retention experiment:

  none        pass the history through unchanged (full attention; arm A, and the zend arms)
  recency     keep the task + the last K turns, then older turns newest-first until the budget is spent
  relevance   keep the task + the last K turns, then older turns ranked by similarity to the
              current query (last assistant message + last observation) until the budget is spent
  compaction  when over budget, fold everything older than the last K turns into one running
              summary written by the model itself (threshold-compression), keep summary + last K

All three spend the SAME token budget, measured with the same counter, so the comparison is at
matched footprint. The engine is never touched; only the messages it is sent change.

Units
-----
A *turn* is one assistant message plus the tool message(s) that answer its tool calls. Turns are the
atomic unit kept or dropped, so an assistant tool_call is never separated from its result (the
OpenAI chat format requires the pair). The system prompt and the first user message (the task) are
always kept, as is a final dangling user message if the agent sends one.

Token counting uses tiktoken (cl100k_base) when available, else len/4. It is an approximation of
the Qwen tokenizer; what matters is that every arm is measured with the same ruler.

Embedders for `relevance`: "bow" is a dependency-free hashed TF-IDF cosine (a BM25-flavoured dumb
baseline); any other name is loaded with sentence-transformers (e.g. BAAI/bge-small-en-v1.5).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

# ── token counting ───────────────────────────────────────────────────────────

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
    TOKENIZER = "tiktoken/cl100k_base"

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text, disallowed_special=()))
except Exception:  # noqa: BLE001 - tiktoken optional (or its BPE file unreachable)
    _ENC = None
    TOKENIZER = "chars/4"

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)
# TOKENIZER is recorded per run (summary.json) because the two rulers differ by ~1.5x on code and a
# matched-budget comparison is only matched if every arm was measured with the same one.


def msg_text(m: dict) -> str:
    """Everything in a message that costs tokens, flattened to text."""
    parts = []
    c = m.get("content")
    if isinstance(c, str):
        parts.append(c)
    elif isinstance(c, list):
        for p in c:
            parts.append(p.get("text", "") if isinstance(p, dict) else str(p))
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function") or {}
        parts.append(fn.get("name", "") + " " + (fn.get("arguments") or ""))
    return "\n".join(parts)


def msg_tokens(m: dict) -> int:
    return count_tokens(msg_text(m)) + 4  # per-message overhead, roughly


# ── turn segmentation ────────────────────────────────────────────────────────

@dataclass
class Turn:
    index: int                 # 0-based position in the turn sequence
    messages: list             # assistant message + its tool replies (or a lone user/assistant msg)
    tokens: int = 0
    key: str = ""              # stable hash for embedding caches

    def text(self) -> str:
        return "\n".join(msg_text(m) for m in self.messages)


def segment(messages: list[dict]) -> tuple[list[dict], list[Turn], list[dict]]:
    """Split into (head, turns, tail).

    head: system message(s) and the first user message (the task) - always kept.
    turns: the dialogue after the task, grouped so tool replies travel with their assistant call.
    tail: a trailing user message with no assistant answer yet (rare with mini-swe-agent) - always kept.
    """
    head, rest = [], []
    seen_user = False
    for m in messages:
        if not seen_user and m.get("role") in ("system", "developer"):
            head.append(m)
        elif not seen_user and m.get("role") == "user":
            head.append(m)
            seen_user = True
        else:
            rest.append(m)
    tail = []
    if rest and rest[-1].get("role") == "user":
        tail = [rest.pop()]
    turns: list[Turn] = []
    cur: list[dict] = []
    for m in rest:
        if m.get("role") == "tool" and cur:
            cur.append(m)
        else:
            if cur:
                turns.append(Turn(len(turns), cur))
            cur = [m]
    if cur:
        turns.append(Turn(len(turns), cur))
    for t in turns:
        t.tokens = sum(msg_tokens(m) for m in t.messages)
        t.key = hashlib.sha1(t.text().encode()).hexdigest()[:16]
    return head, turns, tail


def truncate_turn(t: Turn, max_tokens: int) -> Turn:
    """Return a copy of a turn whose tool outputs are clipped head+tail to fit max_tokens.

    Only applied to *retrieved history* turns, never to the last-K window, so the agent always sees
    its most recent observations whole. Clipping rather than splitting is the v1 simplification
    (noted in the plan); the marker makes it visible to the model.
    """
    if t.tokens <= max_tokens:
        return t
    msgs = [dict(m) for m in t.messages]
    tool_msgs = [m for m in msgs if m.get("role") == "tool" and isinstance(m.get("content"), str)]
    if not tool_msgs:
        return t
    fixed = sum(msg_tokens(m) for m in msgs if m not in tool_msgs)
    per = max(64, (max_tokens - fixed) // len(tool_msgs))
    for m in tool_msgs:
        c = m["content"]
        if count_tokens(c) > per:
            half = max(1, per * 2)  # ~chars per half (4 chars/token, two halves)
            m["content"] = c[:half] + f"\n…[{count_tokens(c) - per} tokens elided by context policy]…\n" + c[-half:]
    nt = Turn(t.index, msgs, key=t.key)
    nt.tokens = sum(msg_tokens(m) for m in msgs)
    return nt


# ── embedders ────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+|[^\sA-Za-z0-9_]")


class BowEmbedder:
    """Hashed TF-IDF-ish cosine over a running vocabulary. No dependencies. Deterministic.

    IDF is computed over the turns currently indexed for this conversation, so a token that appears
    in every turn (the prompt boilerplate, 'bash') carries no weight.
    """
    name = "bow"

    def __init__(self, dims: int = 1 << 16):
        self.dims = dims

    @staticmethod
    def _terms(text: str) -> list[str]:
        return [t.lower() for t in _TOKEN_RE.findall(text)]

    def _tf(self, text: str) -> Counter:
        return Counter(hash(t) % self.dims for t in self._terms(text))

    def rank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        tfs = [self._tf(d) for d in docs]
        df: Counter = Counter()
        for tf in tfs:
            df.update(tf.keys())
        n = len(docs)
        idf = {k: math.log(1 + n / (1 + v)) for k, v in df.items()}
        q = self._tf(query)
        qv = {k: (1 + math.log(v)) * idf.get(k, math.log(1 + n)) for k, v in q.items()}
        qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
        out = []
        for tf in tfs:
            dv = {k: (1 + math.log(v)) * idf[k] for k, v in tf.items()}
            dn = math.sqrt(sum(x * x for x in dv.values())) or 1.0
            dot = sum(w * dv.get(k, 0.0) for k, w in qv.items())
            out.append(dot / (qn * dn))
        return out


class SentenceEmbedder:
    """sentence-transformers wrapper with a per-text cache (turns are re-ranked every step)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # heavy import, only when asked for
        self.name = model_name
        self.model = SentenceTransformer(model_name)
        self.cache: dict[str, list[float]] = {}

    def _embed(self, texts: list[str]) -> list[list[float]]:
        todo = [t for t in texts if t not in self.cache]
        if todo:
            vecs = self.model.encode(todo, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
            for t, v in zip(todo, vecs):
                self.cache[t] = [float(x) for x in v]
        return [self.cache[t] for t in texts]

    def rank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        qv = self._embed([query])[0]
        dvs = self._embed(docs)
        return [sum(a * b for a, b in zip(qv, dv)) for dv in dvs]


def make_embedder(name: str):
    return BowEmbedder() if name in ("bow", "", None) else SentenceEmbedder(name)


# ── policies ─────────────────────────────────────────────────────────────────

@dataclass
class PolicyConfig:
    policy: str = "none"             # none | recency | relevance | compaction
    budget_tokens: int = 32768       # hard cap on what the engine is sent (head + kept turns + tail)
    keep_last: int = 4               # turns always kept verbatim at the end
    max_turn_tokens: int = 1024      # clip for retrieved history turns (not the last-K window)
    embed_model: str = "bow"
    chronological: bool = True       # relevance: re-order retrieved turns by time (else by score)
    max_summary_tokens: int = 1500   # compaction: size of the running summary the model is asked for
    clip_recent: bool = False        # hard cap: clip the last-K window too, and drop oldest kept turns until under budget


@dataclass
class PolicyStats:
    policy: str
    turns_total: int
    turns_kept: int
    tokens_before: int
    tokens_after: int
    kept_indices: list = field(default_factory=list)
    summarised: int = 0              # compaction: turns folded into the summary this call

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["kept_indices"] = d["kept_indices"][:200]
        return d


class ConversationState:
    """Per-conversation memory the compaction policy needs (the running summary)."""

    def __init__(self):
        self.summary: Optional[str] = None
        self.summary_through: int = -1   # turn index the summary covers up to (inclusive)
        self.embedder = None


SUMMARY_PROMPT = (
    "You are compressing the earlier part of a software-engineering session so an agent can continue "
    "from it. Write a dense, factual summary (max ~{n} tokens) that preserves: the task; files and "
    "symbols located; commands run and their outcomes; errors seen and what they meant; approaches "
    "tried and whether they worked; the current state of any edits; and what remains to do. Use terse "
    "bullets. Do not add advice or filler."
)


def _total(head, turns, tail) -> int:
    return sum(msg_tokens(m) for m in head) + sum(t.tokens for t in turns) + sum(msg_tokens(m) for m in tail)


def apply_policy(messages: list[dict], cfg: PolicyConfig, state: ConversationState,
                 summarise: Optional[Callable[[str], str]] = None) -> tuple[list[dict], PolicyStats]:
    """Return (new_messages, stats). `summarise(prompt_text) -> summary` is required for compaction."""
    head, turns, tail = segment(messages)
    before = _total(head, turns, tail)
    n = len(turns)
    base = PolicyStats(cfg.policy, n, n, before, before, list(range(n)))

    if cfg.policy == "none" or n == 0 or before <= cfg.budget_tokens:
        return messages, base

    fixed = sum(msg_tokens(m) for m in head) + sum(msg_tokens(m) for m in tail)
    recent = turns[-cfg.keep_last:] if cfg.keep_last > 0 else []
    older = turns[:-cfg.keep_last] if cfg.keep_last > 0 else list(turns)
    if cfg.clip_recent:
        # hard-cap mode: the recent window is clipped like any other turn (soft mode keeps the latest
        # observations whole, which is why P1's soft-32K arms peaked at 53-65K)
        recent = [truncate_turn(t, cfg.max_turn_tokens) for t in recent]
    budget_left = cfg.budget_tokens - fixed - sum(t.tokens for t in recent)

    if cfg.policy == "recency":
        chosen: list[Turn] = []
        for t in reversed(older):
            tt = truncate_turn(t, cfg.max_turn_tokens)
            if tt.tokens <= budget_left:
                chosen.append(tt)
                budget_left -= tt.tokens
            else:
                break
        kept = sorted(chosen, key=lambda t: t.index) + recent

    elif cfg.policy == "relevance":
        if state.embedder is None:
            state.embedder = make_embedder(cfg.embed_model)
        q_parts = []
        for t in recent[-1:] or []:
            q_parts.append(t.text())
        if tail:
            q_parts.append(msg_text(tail[-1]))
        query = "\n".join(q_parts) or msg_text(head[-1])
        scores = state.embedder.rank(query, [t.text() for t in older])
        order = sorted(range(len(older)), key=lambda i: scores[i], reverse=True)
        chosen = []
        for i in order:
            tt = truncate_turn(older[i], cfg.max_turn_tokens)
            if tt.tokens <= budget_left:
                chosen.append(tt)
                budget_left -= tt.tokens
            if budget_left < 64:
                break
        if cfg.chronological:
            chosen.sort(key=lambda t: t.index)
        kept = chosen + recent

    elif cfg.policy == "compaction":
        if summarise is None:
            raise RuntimeError("compaction policy needs a summarise() callable")
        # Fold everything older than the recent window into the running summary. Incremental: the
        # previous summary plus only the turns it does not yet cover go to the model.
        new_turns = [t for t in older if t.index > state.summary_through]
        if new_turns or state.summary is None:
            body = ""
            if state.summary:
                body += "Previous summary:\n" + state.summary + "\n\nNew events since then:\n"
            body += "\n\n".join(f"[turn {t.index}]\n{truncate_turn(t, 2 * cfg.max_turn_tokens).text()}" for t in new_turns)
            prompt = SUMMARY_PROMPT.format(n=cfg.max_summary_tokens) + "\n\n" + body
            state.summary = summarise(prompt)
            state.summary_through = older[-1].index if older else state.summary_through
            base.summarised = len(new_turns)
        summary_msg = {"role": "user", "content": "Summary of the session so far (earlier steps were compacted):\n" + (state.summary or "")}
        if cfg.clip_recent:
            while len(recent) > 1 and fixed + msg_tokens(summary_msg) + sum(t.tokens for t in recent) > cfg.budget_tokens:
                recent = recent[1:]
        out = head + [summary_msg] + [m for t in recent for m in t.messages] + tail
        stats = PolicyStats(cfg.policy, n, len(recent), before, sum(msg_tokens(m) for m in out),
                            [t.index for t in recent], base.summarised)
        return out, stats

    else:
        raise ValueError(f"unknown policy {cfg.policy}")

    if cfg.clip_recent:
        # enforce the cap: drop the oldest kept turn until the assembled prompt fits (the last turn
        # is always kept so the model sees the observation it must act on)
        while len(kept) > 1 and fixed + sum(t.tokens for t in kept) > cfg.budget_tokens:
            kept.pop(0)
    out = head + [m for t in kept for m in t.messages] + tail
    stats = PolicyStats(cfg.policy, n, len(kept), before, sum(msg_tokens(m) for m in out), [t.index for t in kept])
    return out, stats


def describe(cfg: PolicyConfig) -> str:
    if cfg.policy == "none":
        return "none"
    s = f"{cfg.policy} budget={cfg.budget_tokens}{' HARD' if cfg.clip_recent else ' soft'} keep_last={cfg.keep_last} clip={cfg.max_turn_tokens}"
    if cfg.policy == "relevance":
        s += f" embed={cfg.embed_model} order={'time' if cfg.chronological else 'score'}"
    if cfg.policy == "compaction":
        s += f" summary<= {cfg.max_summary_tokens}"
    return s
