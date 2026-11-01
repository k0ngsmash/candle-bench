"""Logging proxy between the agent and a backend (zend, vLLM or llama.cpp), with optional
context-retention policies.

With --policy none (default) every request is forwarded unchanged. With recency / relevance /
compaction the message list is rewritten per context_policy.py before it reaches the engine - the
application-level arms of the retention experiment. One JSON line per completion call is appended
to --log: wall time, status, prompt/completion tokens as the backend reports them, a short hash of
the opening user message so calls group per task, and (when a policy is on) what the policy did.
Non-streaming only, which is what mini-swe-agent uses.
"""
import argparse
import asyncio
import hashlib
import json
import time
import urllib.request
from collections import defaultdict

from aiohttp import ClientSession, ClientTimeout, web

from context_policy import ConversationState, PolicyConfig, apply_policy, describe, make_embedder


def conversation_tag(body: dict) -> str:
    for m in body.get("messages", []):
        if m.get("role") == "user":
            c = m.get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            return hashlib.sha1(text.encode()).hexdigest()[:10]
    return "-"


def make_summariser(upstream: str, model: str, max_tokens: int, log_path: str):
    """Synchronous side call to the same engine, used by the compaction policy. Logged separately."""
    def summarise(prompt: str) -> str:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": 0.2}
        req = urllib.request.Request(upstream + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=1800) as r:
            resp = json.loads(r.read())
        text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        with open(log_path, "a") as f:
            f.write(json.dumps({"t_start": round(t0, 3), "seconds": round(time.time() - t0, 3), "kind": "summary",
                                "prompt_tokens": (resp.get("usage") or {}).get("prompt_tokens"),
                                "completion_tokens": (resp.get("usage") or {}).get("completion_tokens")}) + "\n")
        return text.strip()
    return summarise


async def handle(request: web.Request) -> web.Response:
    app = request.app
    raw = await request.read()
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    is_chat = request.path.endswith("/chat/completions") and bool(body.get("messages"))
    conv = conversation_tag(body)          # before any change, so calls group by task
    policy_stats = None
    if is_chat and app["cfg"].policy != "none":
        state = app["conv_state"][conv]
        state.embedder = app["embedder"]
        loop = asyncio.get_running_loop()
        # apply_policy may embed or make a summary side call - keep it off the event loop
        new_msgs, stats = await loop.run_in_executor(
            None, apply_policy, body["messages"], app["cfg"], state, app["summarise"])
        body["messages"] = new_msgs
        policy_stats = stats.as_dict()
        raw = json.dumps(body).encode()
    if is_chat and app["fresh"]:
        # Make every call a new conversation to zend, so it rebuilds the context from the client's
        # history (answers and tool calls, no earlier reasoning) instead of the context it holds.
        app["state"]["n"] += 1
        for m in body["messages"]:
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                m["content"] += f"\n\n(request {app['state']['n']})"
                break
        raw = json.dumps(body).encode()
    t0 = time.time()
    async with app["session"].request(
        request.method, app["upstream"] + request.path_qs, data=raw,
        headers={"content-type": request.headers.get("content-type", "application/json")},
    ) as up:
        data = await up.read()
        status = up.status
        ctype = up.headers.get("content-type", "application/json")
    t1 = time.time()
    if request.path.endswith("/chat/completions"):
        usage, finish, n_calls = {}, None, 0
        try:
            resp = json.loads(data)
            usage = resp.get("usage") or {}
            choice = (resp.get("choices") or [{}])[0]
            finish = choice.get("finish_reason")
            n_calls = len((choice.get("message") or {}).get("tool_calls") or [])
        except ValueError:
            pass
        rec = {
            "t_start": round(t0, 3), "seconds": round(t1 - t0, 3), "status": status,
            "conv": conv, "n_messages": len(body.get("messages", [])),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "finish_reason": finish, "tool_calls": n_calls,
        }
        if policy_stats:
            rec["policy"] = policy_stats
        with open(app["log"], "a") as f:
            f.write(json.dumps(rec) + "\n")
    return web.Response(body=data, status=status, content_type=ctype.split(";")[0])


async def on_startup(app):
    app["session"] = ClientSession(timeout=ClientTimeout(total=3600))


async def on_cleanup(app):
    await app["session"].close()


def build_app(a) -> web.Application:
    cfg = PolicyConfig(policy=a.policy, budget_tokens=a.budget_tokens, keep_last=a.keep_last,
                       max_turn_tokens=a.max_turn_tokens, embed_model=a.embed_model,
                       chronological=not a.score_order, max_summary_tokens=a.max_summary_tokens)
    app = web.Application(client_max_size=256 * 1024 * 1024)
    upstream = a.upstream.rstrip("/")
    app.update(upstream=upstream, log=a.log, fresh=a.fresh_context, state={"n": 0}, cfg=cfg,
               conv_state=defaultdict(ConversationState),
               embedder=make_embedder(cfg.embed_model) if cfg.policy == "relevance" else None,
               summarise=make_summariser(upstream, a.model, cfg.max_summary_tokens, a.log) if cfg.policy == "compaction" else None)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--listen", type=int, required=True)
    p.add_argument("--upstream", required=True, help="e.g. http://127.0.0.1:8090")
    p.add_argument("--log", required=True)
    p.add_argument("--fresh-context", action="store_true")
    p.add_argument("--policy", default="none", choices=["none", "recency", "relevance", "compaction"])
    p.add_argument("--budget-tokens", type=int, default=32768)
    p.add_argument("--keep-last", type=int, default=4)
    p.add_argument("--max-turn-tokens", type=int, default=1024)
    p.add_argument("--embed-model", default="bow", help="'bow' (built-in) or a sentence-transformers model name")
    p.add_argument("--score-order", action="store_true", help="relevance: order retrieved turns by score, not time")
    p.add_argument("--max-summary-tokens", type=int, default=1500)
    p.add_argument("--model", default="passthrough", help="model name for compaction side calls")
    a = p.parse_args()
    app = build_app(a)
    print(f"proxy :{a.listen} -> {a.upstream}  policy: {describe(app['cfg'])}", flush=True)
    web.run_app(app, host="127.0.0.1", port=a.listen, print=None)


if __name__ == "__main__":
    main()
