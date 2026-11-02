"""Linux port of harness/run_bench.py for a native cloud box (no WSL, no PowerShell).

Only the platform-coupled parts differ from the thor version:
  - zend is launched directly from its binary (ZEND_BIN) instead of start-zend.ps1;
  - nvidia-smi is the native one;
  - the disk guard watches the box's work filesystem, not D:;
  - the vLLM launch drops the WSL-only PATH/pin-memory workarounds.
The agent, proxy, scoring, sampling, step limit and outputs are identical to the thor runs, so
numbers slot straight into agent-bench/results.

  ZEND_BIN=cloud/bin/zend-win131072 ZEND_WS=~/zend-ws \
    python run_bench_linux.py --backend zend --tasks-file ../stuck15.txt --workers 1 --label win128k
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../agent-bench/cloud
BENCH = HERE.parent                                  # .../agent-bench
HARNESS = BENCH / "harness"                          # proxy.py, summarize.py live here
HOME = Path.home()
VLLM = HOME / "venvs/vllm/bin/vllm"
AGENT_BIN = HOME / "venvs/agent/bin"
NVSMI = "nvidia-smi"
PROXY_PORT = 9000
ZEND_URL = "http://127.0.0.1:8090"
ZEND_BIN = Path(os.environ.get("ZEND_BIN", HERE / "bin" / "zend-win32768"))
ZEND_WS = Path(os.environ.get("ZEND_WS", HOME / "zend-ws"))
BENCH_DISK = os.environ.get("BENCH_DISK", str(HOME))   # zend writes its substrate under the workspace
VLLM_URL = "http://127.0.0.1:8000"
VLLM_MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"
# second model family for P4: hf id + the vLLM parser flags that model needs. The agent sees
# "passthrough" either way, so nothing in the harness or sampling changes with the model.
MODELS = {
    "qwen36": ("cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
               ["--tool-call-parser", "qwen3_coder", "--reasoning-parser", "qwen3", "--limit-mm-per-prompt", '{"image":0,"video":0}']),
    "gptoss120b": ("openai/gpt-oss-120b",
                   ["--tool-call-parser", "openai", "--reasoning-parser", "openai_gptoss"]),
    # Mistral family, 24B dense FP8, not a reasoning model; on the official SWE-bench leaderboard
    # with mini-SWE-agent, i.e. its tool calls are known to work under this harness.
    "devstral2": ("mistralai/Devstral-Small-2-24B-Instruct-2512",
                  ["--tool-call-parser", "mistral"]),
}
LLAMA_URL = "http://127.0.0.1:8001"
LLAMA_SERVER = HOME / "llama.cpp/build/bin/llama-server"
LLAMA_GGUF = HOME / "models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

SAMPLING = {"temperature": 0.7, "top_p": 0.95,
            "extra_body": {"top_k": 20, "repetition_penalty": 1.05}}
STEP_LIMIT = 75
MAX_TOKENS = 16384


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def http_ok(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300, r.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# ── backends ────────────────────────────────────────────────────────────────

class Zend:
    proc = None


def stop_zend():
    if Zend.proc and Zend.proc.poll() is None:
        Zend.proc.terminate()
        try:
            Zend.proc.wait(60)
        except subprocess.TimeoutExpired:
            Zend.proc.kill()
    Zend.proc = None
    subprocess.run(["pkill", "-f", "release/zend"], capture_output=True)
    subprocess.run(["pkill", "-f", f"cloud/bin/{ZEND_BIN.name}"], capture_output=True)   # a reused (inherited) zend
    time.sleep(3)


def start_zend(run_dir, zend_env=()):
    """Launch the zend binary directly (passthrough, standalone) and poll /v1/status."""
    if not ZEND_BIN.exists():
        raise RuntimeError(f"zend binary not found: {ZEND_BIN} (build it with 02-build-zend.sh)")
    if not (ZEND_WS / "agent.yaml").exists():
        raise RuntimeError(f"workspace not set up: {ZEND_WS}/agent.yaml (run 02b-workspace.sh)")
    log(f"starting zend {ZEND_BIN.name} (standalone, passthrough)" + (f" with {' '.join(zend_env)}" if zend_env else ""))
    env = dict(os.environ)
    env.setdefault("CUDA_HOME", "/usr/local/cuda")
    env["PATH"] = "/usr/local/cuda/bin:" + env.get("PATH", "")
    env.setdefault("HF_HOME", str(HOME / "hf-cache"))
    for e in zend_env:
        k, v = e.split("=", 1)
        env[k] = v
    args = [str(ZEND_BIN), "--host", "127.0.0.1", "--port", "8090",
            "--agent", str(ZEND_WS / "agent.yaml"), "--working-dir", str(ZEND_WS),
            "--disable-layer", "repo_map", "--disable-layer", "code_reading"]
    out = open(run_dir / "zend.out", "w")
    Zend.proc = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=str(ZEND_WS))
    t0 = time.time()
    while time.time() - t0 < 2400:
        time.sleep(10)
        if Zend.proc.poll() is not None:
            tail = "".join(open(run_dir / "zend.out", errors="replace").readlines()[-40:])
            raise RuntimeError(f"zend exited early ({Zend.proc.returncode}); tail:\n{tail}")
        ok, body = http_ok(f"{ZEND_URL}/v1/status")
        if ok and '"state":"ready"' in body.replace(" ", ""):
            log(f"zend ready after {time.time()-t0:.0f}s")
            return ZEND_URL
        log(f"waiting for zend ({time.time()-t0:.0f}s): {'loading' if ok else 'not answering yet'}")
    raise RuntimeError(f"zend not ready after 40 minutes - see {run_dir/'zend.out'}")


class Vllm:
    proc = None


def stop_vllm():
    if Vllm.proc and Vllm.proc.poll() is None:
        Vllm.proc.send_signal(signal.SIGINT)
        try:
            Vllm.proc.wait(60)
        except subprocess.TimeoutExpired:
            Vllm.proc.kill()
    Vllm.proc = None
    subprocess.run(["pkill", "-f", "vllm serve"], capture_output=True)
    time.sleep(5)


def start_vllm(run_dir, offloads, max_len, model="qwen36"):
    hf_id, parser_args = MODELS[model]
    for off in offloads:
        args = [str(VLLM), "serve", hf_id, "--served-model-name", "passthrough",
                "--host", "127.0.0.1", "--port", "8000",
                "--max-model-len", str(max_len), "--gpu-memory-utilization", "0.90",
                "--max-num-seqs", "8", "--enable-auto-tool-choice", *parser_args]
        # On 96 GB the 35B needs no CPU offload; 0 means "all on GPU". Kept configurable for headroom tests.
        if off:
            args += ["--cpu-offload-gb", str(off)]
        vlog = run_dir / f"vllm-offload{off}.log"
        log(f"starting vLLM (cpu-offload-gb={off}, max-model-len={max_len}) -> {vlog.name}")
        env = dict(os.environ)
        if Path("/usr/local/cuda/bin/nvcc").exists():
            env["CUDA_HOME"] = "/usr/local/cuda"
            env["PATH"] = "/usr/local/cuda/bin:" + env.get("PATH", "")
        Vllm.proc = subprocess.Popen(args, stdout=open(vlog, "w"), stderr=subprocess.STDOUT, env=env)
        t0 = time.time()
        while time.time() - t0 < 1800:
            time.sleep(10)
            if Vllm.proc.poll() is not None:
                log(f"vLLM exited ({Vllm.proc.returncode}) with offload {off}; tail:\n" +
                    "".join(open(vlog, errors="replace").readlines()[-15:]))
                break
            if http_ok(f"{VLLM_URL}/health")[0]:
                log(f"vLLM ready after {time.time()-t0:.0f}s with cpu-offload-gb={off}")
                (run_dir / "vllm-config.json").write_text(json.dumps({"cpu_offload_gb": off, "max_model_len": max_len, "args": args}, indent=1))
                return VLLM_URL
        stop_vllm()
    raise RuntimeError("vLLM could not start with any offload setting tried")


def gpu_sampler(path, stop):
    with open(path, "w") as f:
        f.write("t,mem_used_mib,util_pct,power_w\n")
        while not stop.is_set():
            r = subprocess.run([NVSMI, "--query-gpu=memory.used,utilization.gpu,power.draw",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True)
            f.write(f"{time.time():.1f},{r.stdout.strip().replace(' ', '')}\n")
            f.flush()
            stop.wait(2)


def preflight_call(run_dir):
    code = (
        "import litellm, json, sys\n"
        "from minisweagent.models.utils.actions_toolcall import BASH_TOOL\n"
        f"r = litellm.completion(model='openai/passthrough', api_base='http://127.0.0.1:{PROXY_PORT}/v1', api_key='none',\n"
        "    messages=[{'role':'system','content':'You are a software engineer in a Linux shell.'},\n"
        "              {'role':'user','content':'List the files in the current directory.'}],\n"
        "    tools=[BASH_TOOL], max_tokens=2048, timeout=600)\n"
        "m = r.choices[0].message\n"
        "print(json.dumps({'tool_calls': [t.function.arguments for t in (m.tool_calls or [])], 'finish': r.choices[0].finish_reason, 'usage': r.usage.model_dump()}))\n"
    )
    r = subprocess.run([str(AGENT_BIN / "python"), "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, MSWEA_COST_TRACKING="ignore_errors"))
    (run_dir / "preflight.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0:
        raise RuntimeError("preflight request failed:\n" + (r.stdout + r.stderr)[-2000:])
    log(f"preflight request ok: {r.stdout.strip()}")


class Llama:
    proc = None


def stop_llama():
    if Llama.proc and Llama.proc.poll() is None:
        Llama.proc.terminate()
        try:
            Llama.proc.wait(60)
        except subprocess.TimeoutExpired:
            Llama.proc.kill()
    Llama.proc = None
    subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    time.sleep(3)


def start_llama(run_dir, cpu_moe_list, max_len, slots):
    for n in cpu_moe_list:
        args = [str(LLAMA_SERVER), "-m", str(LLAMA_GGUF), "--alias", "passthrough", "--jinja",
                "--host", "127.0.0.1", "--port", "8001", "-ngl", "99", "--n-cpu-moe", str(n),
                "-c", str(max_len * slots), "--parallel", str(slots), "--flash-attn", "on", "--metrics"]
        llog = run_dir / f"llama-cpumoe{n}.log"
        log(f"starting llama.cpp (--n-cpu-moe {n}, {slots} slots x {max_len} ctx) -> {llog.name}")
        Llama.proc = subprocess.Popen(args, stdout=open(llog, "w"), stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 900:
            time.sleep(10)
            if Llama.proc.poll() is not None:
                log(f"llama.cpp exited ({Llama.proc.returncode}) with --n-cpu-moe {n}; tail:\n" +
                    "".join(open(llog, errors="replace").readlines()[-12:]))
                break
            if http_ok(f"{LLAMA_URL}/health")[0]:
                log(f"llama.cpp ready after {time.time()-t0:.0f}s with --n-cpu-moe {n}")
                (run_dir / "llama-config.json").write_text(json.dumps({"n_cpu_moe": n, "ctx_per_slot": max_len, "slots": slots, "args": args}, indent=1))
                return LLAMA_URL
        stop_llama()
    raise RuntimeError("llama.cpp could not start with any --n-cpu-moe value tried")


DATASETS = {  # agent subset name, HF dataset for the SWE-bench eval harness
    "lite": ("lite", "SWE-bench/SWE-bench_Lite"),
    "verified": ("verified", "SWE-bench/SWE-bench_Verified"),
}


def task_ids(n, dataset="lite"):
    cache = BENCH / ("instances.txt" if dataset == "lite" else f"instances-{dataset}.txt")
    if not cache.exists():
        from datasets import load_dataset
        ds = load_dataset(DATASETS[dataset][1], split="test")
        cache.write_text("\n".join(ds[i]["instance_id"] for i in range(0, len(ds), 10)) + "\n")
    return cache.read_text().split()[:n]


# Per-model sampling where the model's own recommended settings differ from the Qwen defaults above.
# gpt-oss: OpenAI recommends temperature 1.0 / top_p 1.0 and no penalties; a repetition penalty
# corrupts long tool-call JSON (the tokens that must repeat are quotes, escapes and braces) - the P4
# first attempt hit RepeatedFormatError on 14/15 tasks with the Qwen settings. Qwen is unchanged.
# Per-model proxy flags. gpt-oss emits long bash commands whose tool arguments are almost-JSON
# (raw newlines, unescaped quotes); without repair 14/15 tasks end in RepeatedFormatError and the run
# measures the parser, not the agent. Repairs are logged per call and reported in summary.md.
MODEL_PROXY_FLAGS = {
    "gptoss120b": ["--repair-tool-args"],
}

MODEL_SAMPLING = {
    "gptoss120b": {"temperature": 1.0, "top_p": 1.0, "extra_body": {}},
    "devstral2": {"temperature": 0.15, "extra_body": {}},          # Mistral's recommended setting
}


def overlay(path, max_tokens, repetition_penalty=None, backend="zend", seed=None, model="qwen36"):
    import yaml
    sampling = json.loads(json.dumps(MODEL_SAMPLING.get(model, SAMPLING) if backend == "vllm" else SAMPLING))
    if repetition_penalty is not None:
        sampling["extra_body"]["repetition_penalty"] = repetition_penalty
    if seed is not None:
        sampling["seed"] = seed
    if backend == "llama":
        sampling["extra_body"]["repeat_penalty"] = sampling["extra_body"].pop("repetition_penalty")
    cfg = {
        "agent": {"step_limit": STEP_LIMIT, "cost_limit": 0},
        "model": {
            "model_name": "openai/passthrough",
            "model_kwargs": {"api_base": f"http://127.0.0.1:{PROXY_PORT}/v1", "api_key": "none",
                             "timeout": 3600, "max_tokens": max_tokens, **sampling},
            "cost_tracking": "ignore_errors",
        },
    }
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))


NOTES_TEXT = """

Working notes: keep the file /tmp/notes.md as your memory for this task. After any command that teaches
you something (where a file is, how to run the tests, an error, an approach that failed), append one short
line to it with echo >> /tmp/notes.md. Before running a command like one you have run before, run
cat /tmp/notes.md first, and do not repeat an approach the notes say has failed.
"""


def notes_config(path):
    import yaml
    import minisweagent
    found = sorted(Path(minisweagent.__file__).parent.rglob("swebench.yaml"))
    if not found:
        raise RuntimeError("swebench.yaml not found in the mini-swe-agent package")
    base = yaml.safe_load(found[0].read_text())
    template = (base.get("agent") or {}).get("instance_template")
    if not template:
        raise RuntimeError(f"no agent.instance_template in {found[0]}")
    path.write_text(yaml.safe_dump({"agent": {"instance_template": template + NOTES_TEXT}}, sort_keys=False))
    log(f"working-notes instruction appended to the template from {found[0]}")


def score(run_dir, ids, dataset="lite"):
    preds = run_dir / "agent" / "preds.json"
    if not preds.exists():
        return None
    log("scoring with the SWE-bench harness")
    run_id = run_dir.name
    with open(run_dir / "eval.log", "w") as f:
        subprocess.run([str(AGENT_BIN / "python"), "-m", "swebench.harness.run_evaluation",
                        "--dataset_name", DATASETS[dataset][1], "--split", "test",
                        "--predictions_path", str(preds), "--max_workers", "4", "--run_id", run_id,
                        "--instance_ids", *ids], cwd=run_dir, stdout=f, stderr=subprocess.STDOUT)
    reports = list(run_dir.glob(f"*.{run_id}.json"))
    if not reports:
        log(f"no score report - see {run_dir/'eval.log'}")
        return None
    rep = json.loads(reports[0].read_text())
    return {"resolved": rep.get("resolved_instances"), "submitted": rep.get("submitted_instances"),
            "empty_patches": rep.get("empty_patch_instances"), "errors": rep.get("error_instances"),
            "resolved_ids": rep.get("resolved_ids", [])}


def rescore(run_dir):
    ids = (run_dir / "tasks.txt").read_text().split()
    s = json.loads((run_dir / "summary.json").read_text())
    s["score"] = score(run_dir, ids, s.get("dataset", "lite"))
    (run_dir / "summary.json").write_text(json.dumps(s, indent=1))
    subprocess.run([str(AGENT_BIN / "python"), str(HARNESS / "summarize.py"), str(run_dir)])


def stop_backend(backend):
    {"zend": stop_zend, "vllm": stop_vllm, "llama": stop_llama}[backend]()
    BACKEND_STATE.unlink(missing_ok=True)


BACKEND_STATE = HOME / ".bench-backend.json"   # what is currently serving, written on a successful start
HEALTH = {"zend": f"{ZEND_URL}/v1/status", "vllm": f"{VLLM_URL}/health", "llama": f"{LLAMA_URL}/health"}


def backend_signature(a) -> dict:
    """Everything that would make two backend starts different, so reuse is only ever like-for-like."""
    if a.backend == "zend":
        detail = f"{ZEND_BIN.name} env={sorted(a.zend_env)}"
    elif a.backend == "vllm":
        detail = f"{MODELS[a.model][0]} max_len={a.max_model_len} offloads={a.offloads}"
    else:
        detail = f"{LLAMA_GGUF.name} max_len={a.max_model_len} slots={max(a.workers, 1)} cpu_moe={a.cpu_moe}"
    return {"backend": a.backend, "detail": detail}


def reuse_backend(want: dict):
    """URL of a running backend matching `want`, else None. Never reuses across a config change."""
    if not BACKEND_STATE.exists():
        return None
    try:
        have = json.loads(BACKEND_STATE.read_text())
    except ValueError:
        return None
    if have != want:
        log(f"backend up but different ({have.get('backend')}: {have.get('detail')}) - restarting")
        return None
    ok, body = http_ok(HEALTH[want["backend"]])
    if not ok or (want["backend"] == "zend" and '"state":"ready"' not in body.replace(" ", "")):
        log("backend state file present but the server is not healthy - restarting")
        BACKEND_STATE.unlink(missing_ok=True)
        return None
    # the stop_* helpers pkill by pattern, so an inherited process is still stoppable at the end
    return {"zend": ZEND_URL, "vllm": VLLM_URL, "llama": LLAMA_URL}[want["backend"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["zend", "vllm", "llama"])
    ap.add_argument("--cpu-moe", default="8,12,16,20")
    ap.add_argument("--tasks", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--label", default="run")
    ap.add_argument("--offloads", default="0", help="vLLM --cpu-offload-gb values; 0 = all on GPU (96 GB fits the 35B)")
    ap.add_argument("--max-model-len", type=int, default=65536)
    ap.add_argument("--keep-backend", action="store_true")
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--rescore", metavar="RUN_DIR")
    ap.add_argument("--repetition-penalty", type=float)
    ap.add_argument("--tasks-file")
    ap.add_argument("--dataset", default="lite", choices=list(DATASETS), help="SWE-bench subset the task ids belong to (agent env + grading)")
    ap.add_argument("--model", default="qwen36", choices=list(MODELS), help="vLLM model (the agent always sees 'passthrough')")
    ap.add_argument("--fresh-context", action="store_true")
    ap.add_argument("--notes", action="store_true")
    ap.add_argument("--zend-env", action="append", default=[], metavar="KEY=VALUE")
    # context-retention policy (the application-level arms; applied in the proxy, engine untouched)
    ap.add_argument("--policy", default="none", choices=["none", "recency", "relevance", "compaction"])
    ap.add_argument("--budget-tokens", type=int, default=32768, help="matched footprint cap for recency/relevance/compaction")
    ap.add_argument("--keep-last", type=int, default=4)
    ap.add_argument("--max-turn-tokens", type=int, default=1024)
    ap.add_argument("--embed-model", default="bow", help="relevance: 'bow' or a sentence-transformers model")
    ap.add_argument("--score-order", action="store_true")
    ap.add_argument("--max-summary-tokens", type=int, default=1500)
    ap.add_argument("--clip-recent", action="store_true", help="hard cap: clip the last-K window too; the prompt never exceeds --budget-tokens")
    ap.add_argument("--strip-reasoning", action="store_true", help="remove the agent's past reasoning_content from the history (any policy)")
    ap.add_argument("--seed", type=int, help="sampling seed passed to the engine (fixed seeds per rep)")
    a = ap.parse_args()
    if a.rescore:
        rescore(Path(a.rescore).resolve())
        return

    ids = Path(a.tasks_file).read_text().split() if a.tasks_file else task_ids(a.tasks, a.dataset)
    pol = ("" if a.policy == "none" else f"_{a.policy}{a.budget_tokens // 1024}k{'hard' if a.clip_recent else ''}") + ("_nothink" if a.strip_reasoning else "")
    mdl = "" if a.model == "qwen36" else f"_{a.model}"
    run_dir = BENCH / "runs" / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{a.label}_{a.backend}{mdl}{pol}_w{a.workers}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks.txt").write_text("\n".join(ids) + "\n")
    log(f"{a.backend}: {len(ids)} tasks, {a.workers} parallel agents -> {run_dir}")

    if a.policy != "none" and a.backend == "zend" and not a.fresh_context:
        # zend's passthrough keeps its own per-conversation context and ignores a rewritten history
        # unless each call is a new conversation; the policy arms are meant for vLLM/llama anyway.
        log("policy arm on zend: forcing --fresh-context so the rewritten history is what zend sees")
        a.fresh_context = True
    if a.notes:
        notes_config(run_dir / "notes.yaml")
    # Reuse a healthy backend left up by a previous --keep-backend run if its config matches; a vLLM
    # start is 3-4 minutes, so back-to-back runs on the same engine should not pay it again.
    want = backend_signature(a)
    upstream = reuse_backend(want)
    if upstream:
        log(f"reusing the running {a.backend} backend ({want['detail']})")
        (run_dir / "backend-reused.json").write_text(json.dumps(want, indent=1))
    else:
        stop_vllm(); stop_llama(); stop_zend(); time.sleep(5)
        if a.backend == "zend":
            if a.zend_env:
                (run_dir / "zend-env.txt").write_text("\n".join(a.zend_env) + "\n")
            upstream = start_zend(run_dir, a.zend_env)
        elif a.backend == "vllm":
            upstream = start_vllm(run_dir, [int(x) for x in a.offloads.split(",")], a.max_model_len, a.model)
        else:
            upstream = start_llama(run_dir, [int(x) for x in a.cpu_moe.split(",")], a.max_model_len, max(a.workers, 1))
        BACKEND_STATE.write_text(json.dumps(want))

    policy_args = ["--policy", a.policy, "--budget-tokens", str(a.budget_tokens), "--keep-last", str(a.keep_last),
                   "--max-turn-tokens", str(a.max_turn_tokens), "--embed-model", a.embed_model,
                   "--max-summary-tokens", str(a.max_summary_tokens)] + (["--score-order"] if a.score_order else []) \
                  + (["--clip-recent"] if a.clip_recent else []) + (["--strip-reasoning"] if a.strip_reasoning else []) \
                  + (MODEL_PROXY_FLAGS.get(a.model, []) if a.backend == "vllm" else [])
    proxy = subprocess.Popen([str(AGENT_BIN / "python"), str(HARNESS / "proxy.py"), "--listen", str(PROXY_PORT),
                              "--upstream", upstream, "--log", str(run_dir / "calls.jsonl")]
                             + (["--fresh-context"] if a.fresh_context else []) + policy_args,
                             stdout=open(run_dir / "proxy.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(3)
    stop = threading.Event()
    sampler = threading.Thread(target=gpu_sampler, args=(run_dir / "gpu.csv", stop), daemon=True)
    sampler.start()

    try:
        preflight_call(run_dir)
    except RuntimeError as e:
        log(str(e))
        stop.set(); proxy.terminate()
        stop_backend(a.backend)
        sys.exit(1)
    overlay(run_dir / "overlay.yaml", MAX_TOKENS, a.repetition_penalty, a.backend, a.seed, a.model)
    extra = ["-c", str(run_dir / "notes.yaml")] if a.notes else []
    filt = "^(" + "|".join(re.escape(i) for i in ids) + ")$"
    env = dict(os.environ, MSWEA_COST_TRACKING="ignore_errors", MSWEA_SILENT_STARTUP="1")
    agent_cmd = [str(AGENT_BIN / "mini-extra"), "swebench", "--subset", DATASETS[a.dataset][0], "--split", "test",
                 "--filter", filt, "-w", str(a.workers), "-o", str(run_dir / "agent"),
                 "-c", "swebench.yaml", "-c", str(run_dir / "overlay.yaml"), *extra, "--environment-class", "docker", "--redo-existing"]
    log("agents running")
    t0 = time.time()
    with open(run_dir / "agent.log", "w") as f:
        agent = subprocess.Popen(agent_cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
        while agent.poll() is None:
            time.sleep(30)
            free_gb = shutil.disk_usage(BENCH_DISK).free / 2**30
            if free_gb < 40:
                log(f"{BENCH_DISK} has {free_gb:.0f} GB free - stopping the agents to protect the disk")
                agent.terminate()
                agent.wait(120)
                break
        rc = agent.returncode
    wall = time.time() - t0
    log(f"agents finished: exit {rc}, {wall/60:.1f} min")
    stop.set(); proxy.terminate()
    if not a.keep_backend:
        stop_backend(a.backend)

    resolved = None if a.no_eval else score(run_dir, ids, a.dataset)
    # which token ruler the proxy's budget used (tiktoken, or chars/4 if its BPE file was unreachable)
    ruler = next((l.split("ruler: ")[1].strip() for l in open(run_dir / "proxy.log", errors="replace") if "ruler: " in l), None)

    summary = {"backend": a.backend, "model": a.model if a.backend == "vllm" else "zend-build", "dataset": a.dataset, "workers": a.workers, "tasks": len(ids), "fresh_context": a.fresh_context, "repetition_penalty": a.repetition_penalty, "wall_seconds": round(wall),
               "agent_exit": rc, "score": resolved, "seed": a.seed,
               "policy": {"policy": a.policy, "budget_tokens": a.budget_tokens, "cap": "hard" if a.clip_recent else "soft", "strip_reasoning": a.strip_reasoning,
                          "keep_last": a.keep_last, "ruler": ruler,
                          "max_turn_tokens": a.max_turn_tokens, "embed_model": a.embed_model,
                          "order": "score" if a.score_order else "time", "max_summary_tokens": a.max_summary_tokens}}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    log(f"summary: {json.dumps(summary)}")
    subprocess.run([str(AGENT_BIN / "python"), str(HARNESS / "summarize.py"), str(run_dir)])


if __name__ == "__main__":
    main()
