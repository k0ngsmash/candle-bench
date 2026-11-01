"""Offline tests for the context policies, the proxy, and the loop metric. No GPU, no model.

  python test_context_policy.py            # unit tests + an end-to-end pass through the proxy
  python test_context_policy.py <traj.json or run_dir>...   # also prints loop metrics for real trajectories
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context_policy import ConversationState, PolicyConfig, apply_policy, count_tokens, msg_tokens, segment, truncate_turn  # noqa: E402
from loopmetrics import actions_from_traj, canonical, cycle_metrics, fit_per_step_reliability, loop_metrics  # noqa: E402


# ── synthetic agent history ──────────────────────────────────────────────────

def synth_history(n_turns: int, big_every: int = 5) -> list[dict]:
    msgs = [{"role": "system", "content": "You are a software engineer in a Linux shell."},
            {"role": "user", "content": "Fix the failing test in astropy/modeling/separable.py (issue #12907)."}]
    for i in range(n_turns):
        cmd = ["ls", "grep -rn separable astropy/", "cat astropy/modeling/separable.py",
               "python -m pytest astropy/modeling/tests/test_separable.py -x", "git diff"][i % 5]
        if i == n_turns - 3:
            cmd = "sed -i 's/cleft/cright/' astropy/modeling/separable.py"   # the distinctive edit step
        if i == n_turns - 1:
            cmd = "grep -n 'cleft\\|_cstack' astropy/modeling/separable.py"  # the current step: asks about the code
        call_id = f"call_{i}"
        msgs.append({"role": "assistant", "content": f"Step {i}: I will run {cmd.split()[0]}.",
                     "reasoning_content": f"thinking about step {i}... " * 150,     # ~4K chars, like a real thinking model
                     "tool_calls": [{"id": call_id, "type": "function",
                                     "function": {"name": "bash", "arguments": json.dumps({"command": cmd})}}]})
        out = f"output of turn {i} for {cmd}\n" + ("x" * 6000 if i % big_every == 0 else "ok\n" * 20)
        if i == 2:   # exactly one early turn holds the code the final step asks about
            out += "\ndef _cstack(left, right):\n    cleft = _coord_matrix(left, 'left', noutp)\n    cright = ...\n"
        msgs.append({"role": "tool", "tool_call_id": call_id, "content": out})
    return msgs


def pairs_intact(msgs):
    """Every tool message must directly follow an assistant message that issued its tool_call_id."""
    open_ids = set()
    for m in msgs:
        if m["role"] == "assistant":
            open_ids = {tc["id"] for tc in m.get("tool_calls") or []}
        elif m["role"] == "tool":
            assert m["tool_call_id"] in open_ids, f"orphan tool reply {m['tool_call_id']}"
        else:
            open_ids = set()
    return True


def total_tokens(msgs):
    return sum(count_tokens(json.dumps(m)) for m in msgs)


def test_reasoning_counted():
    h = synth_history(6)
    a = next(m for m in h if m["role"] == "assistant")
    with_r, without_r = msg_tokens(a), msg_tokens({k: v for k, v in a.items() if k != "reasoning_content"})
    assert with_r > without_r * 5, (with_r, without_r)
    head, turns, _ = segment(h)
    t = truncate_turn(turns[0], 300)
    assert t.tokens <= 300 * 1.2 and "reasoning elided" in t.messages[0]["reasoning_content"], t.tokens
    print(f"reasoning_content counted ({with_r} vs {without_r} tokens) and clipped ({turns[0].tokens} -> {t.tokens}): ok")


def test_segment():
    h = synth_history(12)
    head, turns, tail = segment(h)
    assert [m["role"] for m in head] == ["system", "user"]
    assert len(turns) == 12 and all(len(t.messages) == 2 for t in turns) and tail == []
    print("segment: ok (12 turns, pairs kept)")


def test_policies():
    h = synth_history(40)
    full = total_tokens(h)
    budget = full // 10      # tight enough that clipping alone cannot make everything fit
    for pol in ("recency", "relevance"):
        cfg = PolicyConfig(policy=pol, budget_tokens=budget, keep_last=4, max_turn_tokens=400)
        out, st = apply_policy(h, cfg, ConversationState())
        assert pairs_intact(out)
        assert st.tokens_after <= budget * 1.05, f"{pol}: {st.tokens_after} > {budget}"
        assert out[0]["role"] == "system" and out[1]["role"] == "user"
        assert st.turns_kept < st.turns_total
        # last-K window kept verbatim
        assert out[-1]["content"] == h[-1]["content"] and out[-2]["content"] == h[-2]["content"]
        print(f"{pol}: {st.turns_total} turns -> {st.turns_kept}, {st.tokens_before} -> {st.tokens_after} tokens "
              f"(budget {budget}); kept {st.kept_indices}")
    # relevance must retrieve the one early turn (index 2) that holds the code the current step asks
    # about, while recency - at the same budget - cannot reach back that far
    cfg = PolicyConfig(policy="relevance", budget_tokens=budget, keep_last=1, max_turn_tokens=400)
    out, st = apply_policy(h, cfg, ConversationState())
    assert 2 in st.kept_indices, f"relevance dropped the turn with the code (kept {st.kept_indices})"
    out_r, st_r = apply_policy(h, PolicyConfig(policy="recency", budget_tokens=budget, keep_last=1, max_turn_tokens=400), ConversationState())
    assert 2 not in st_r.kept_indices, "test is not discriminating: recency reached the early turn too"
    print(f"relevance retrieved the code turn that recency could not (recency kept {st_r.kept_indices[0]}..)")
    # hard cap: even when the last-K turns alone exceed the budget, the prompt never does
    big = synth_history(12, big_every=1)                      # every observation is ~6000 chars
    tight = total_tokens(big) // 6
    for pol in ("recency", "relevance"):
        out_s, st_s = apply_policy(big, PolicyConfig(policy=pol, budget_tokens=tight, keep_last=4, max_turn_tokens=300), ConversationState())
        out_h, st_h = apply_policy(big, PolicyConfig(policy=pol, budget_tokens=tight, keep_last=4, max_turn_tokens=300, clip_recent=True), ConversationState())
        assert st_s.tokens_after > tight, f"{pol}: soft cap unexpectedly held ({st_s.tokens_after} <= {tight}) - test not discriminating"
        assert st_h.tokens_after <= tight, f"{pol}: HARD cap exceeded ({st_h.tokens_after} > {tight})"
        assert pairs_intact(out_h) and out_h[-1]["role"] == "tool"
        print(f"hard cap [{pol}]: soft sent {st_s.tokens_after} > {tight}; hard sent {st_h.tokens_after} <= {tight}, kept {st_h.turns_kept} turns")
    out_h, st_h = apply_policy(big, PolicyConfig(policy="compaction", budget_tokens=tight, keep_last=4, clip_recent=True), ConversationState(), lambda p: "SUMMARY")
    assert st_h.tokens_after <= tight and pairs_intact(out_h)
    # under budget: untouched
    cfg = PolicyConfig(policy="recency", budget_tokens=full * 2)
    out, st = apply_policy(h, cfg, ConversationState())
    assert out is h and st.turns_kept == st.turns_total
    print("under-budget passthrough: ok")
    # compaction with a fake summariser, incremental
    calls = []
    def fake_sum(prompt):
        calls.append(prompt)
        return f"SUMMARY#{len(calls)}: did things"
    state = ConversationState()
    cfg = PolicyConfig(policy="compaction", budget_tokens=budget, keep_last=4)
    out, st = apply_policy(h, cfg, state, fake_sum)
    assert pairs_intact(out) and st.summarised == 36 and "SUMMARY#1" in out[2]["content"]
    assert st.tokens_after <= budget
    h2 = h + synth_history(2)[2:]      # two more turns later
    out2, st2 = apply_policy(h2, cfg, state, fake_sum)
    assert st2.summarised == 2 and "Previous summary" in calls[1] and "SUMMARY#2" in out2[2]["content"]
    print(f"compaction: first call folded {st.summarised} turns, second folded {st2.summarised} (incremental): ok")


def test_loop_metrics():
    acts = ["ls", "cat a", "pytest", "pytest", "pytest", "sed x", "pytest", "ls"]
    m = loop_metrics(acts, k=3)
    assert m["max_repeat"] == 4 and m["longest_run"] == 3 and m["loop_onset_3"] == 5 and m["loop_onset_2"] == 4
    assert m["repeat_fraction"] == round(4 / 8, 4) and m["looped_3"] and not m["looped_5plus"]
    assert loop_metrics([], 3)["n_actions"] == 0
    r = fit_per_step_reliability([(True, 10), (True, 20), (False, 40), (False, 60), (True, 15)])
    assert r and 0.9 < r["r"] < 1.0, r
    print(f"loop metric: ok; reliability fit r={r['r']} on toy data")
    # cycles: period, repetitions, onset; broken patterns and scattered re-issues are not cycles
    c = cycle_metrics(["ls", "sed", "pytest", "sed", "pytest", "sed", "pytest", "git"], k=3)
    assert (c["cycle_period"], c["cycle_repeats_max"], c["cycle_onset"], c["cycled_3"]) == (2, 3, 5, True), c
    assert cycle_metrics(list("abbbbc"), k=3)["cycle_period"] == 1                      # stutter is period 1
    assert cycle_metrics(["a", "b", "c", "a", "b", "x", "a", "b", "c"])["cycle_period"] is None
    assert cycle_metrics(["ls", "a", "ls", "b", "ls", "c"])["cycle_period"] is None       # re-issued, not cyclic
    # canonical form: free text and code bodies collapse, paths and short literals survive
    assert canonical("cd /t && python -c \"x=1 # test the fix\"") == canonical("cd /t && python -c \"y=2 # test the issue\"")
    assert canonical("sed -n '1,40p' a/b.py") != canonical("sed -n '41,80p' a/b.py")      # paging is not looping
    assert canonical("cat > f.py << 'EOF'\nprint(1)\nEOF\npython f.py") == "cat f.py && python f.py"
    near = [c for i in range(3) for c in ("cd /t && sed -n '10,50p' a.py", f"cd /t && python -c \"# try A{i}\"", f"cd /t && python -c \"# try B{i}\"")]
    m = loop_metrics(near, 3)
    assert m["cycle_period"] is None and m["ccycle_period"] == 3 and m["ccycled_3"], m   # exact blind, canonical sees it
    print("cycle detector + canonical form: ok")


# ── end to end through the proxy with a fake upstream ────────────────────────

def fake_upstream(port, seen):
    from aiohttp import web
    async def h(req):
        body = await req.json()
        seen.append(body)
        n = sum(count_tokens(json.dumps(m)) for m in body["messages"])
        if body["messages"][-1]["role"] == "user" and "compressing" in body["messages"][0].get("content", "")[:60] + body["messages"][-1]["content"][:60]:
            text = "- summary of earlier work"
        else:
            text = "ok"
        return web.json_response({"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": n, "completion_tokens": 3}})
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app.router.add_route("*", "/{tail:.*}", h)
    web.run_app(app, host="127.0.0.1", port=port, print=None, handle_signals=False)


def test_proxy_e2e(tmp=Path("/tmp/ctxpol-test")):
    tmp.mkdir(exist_ok=True)
    seen = []
    threading.Thread(target=fake_upstream, args=(18090, seen), daemon=True).start()
    time.sleep(1)
    h = synth_history(30)
    budget = total_tokens(h) // 2
    for pol in ("none", "recency", "relevance", "compaction"):
        log = tmp / f"calls-{pol}.jsonl"
        log.unlink(missing_ok=True)
        p = subprocess.Popen([sys.executable, str(HERE / "proxy.py"), "--listen", "18000", "--upstream", "http://127.0.0.1:18090",
                              "--log", str(log), "--policy", pol, "--budget-tokens", str(budget), "--keep-last", "3"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(1.5)
        try:
            seen.clear()
            req = urllib.request.Request("http://127.0.0.1:18000/v1/chat/completions",
                                         data=json.dumps({"model": "passthrough", "messages": h}).encode(),
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                assert r.status == 200
            rec = json.loads(log.read_text().splitlines()[-1])
            fwd = [b for b in seen if b["messages"][0]["role"] == "system"][-1]["messages"]
            assert pairs_intact(fwd)
            if pol == "none":
                assert len(fwd) == len(h) and "policy" not in rec
            else:
                assert rec["policy"]["policy"] == pol and rec["policy"]["tokens_after"] <= budget * 1.05
                assert len(fwd) < len(h)
            print(f"proxy e2e [{pol}]: forwarded {len(fwd)}/{len(h)} messages, upstream saw {rec['prompt_tokens']} tokens"
                  + (f", summary side-calls {sum(1 for l in log.read_text().splitlines() if '\"kind\": \"summary\"' in l)}" if pol == "compaction" else ""))
        finally:
            p.terminate()
            err = p.stderr.read().decode(errors="replace")
            p.wait(5)
            if "Traceback" in err:
                print(err); raise SystemExit(f"proxy crashed under policy {pol}")


def real_trajectories(paths):
    for p in paths:
        p = Path(p)
        files = [p] if p.is_file() else sorted(p.glob("agent/*/*.traj.json")) or sorted(p.rglob("*.traj.json"))
        for f in files:
            d = json.loads(f.read_text())
            acts = actions_from_traj(d)
            m = loop_metrics(acts, 3)
            print(f"{f.parent.name:45s} exit={str((d.get('info') or {}).get('exit_status')):16s} "
                  f"n={m['n_actions']:3d} distinct={m['n_distinct']:3d} max_rep={m['max_repeat']:2d} "
                  f"run={m['longest_run']:2d} frac={m['repeat_fraction']:.2f} onset3={m['loop_onset_3']}")


if __name__ == "__main__":
    test_reasoning_counted(); test_segment(); test_policies(); test_loop_metrics(); test_proxy_e2e()
    print("all tests passed")
    if sys.argv[1:]:
        print("\nreal trajectories:")
        real_trajectories(sys.argv[1:])
