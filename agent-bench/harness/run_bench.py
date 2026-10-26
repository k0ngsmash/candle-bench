"""Run mini-swe-agent on SWE-bench Lite against zend or vLLM on this machine, then score it.

One backend at a time owns the GPU. The agent, tasks, prompts, step limit and
sampling are identical for both; only the server behind the proxy changes.

  python run_bench.py --backend zend --tasks 2 --workers 1 --label smoke
  python run_bench.py --backend vllm --tasks 30 --workers 4 --label main

Outputs go to agent-bench/runs/<date>_<label>_<backend>_w<workers>/.
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

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent                                   # .../candle-bench/agent-bench (on C:, via /mnt/c)
WIN_BENCH = r"C:\Users\k0ng\source\repos\candle-bench\agent-bench"
HOME = Path.home()
VLLM = HOME / "venvs/vllm/bin/vllm"
AGENT_BIN = HOME / "venvs/agent/bin"
NVSMI = "/usr/lib/wsl/lib/nvidia-smi"
PROXY_PORT = 9000
ZEND_URL = "http://127.0.0.1:8090"
VLLM_URL = "http://127.0.0.1:8000"
VLLM_MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"
LLAMA_URL = "http://127.0.0.1:8001"
LLAMA_SERVER = HOME / "llama.cpp/build/bin/llama-server"
# The same checkpoint zend loads (unsloth UD-Q4_K_M, pinned revision), as llama.cpp reads it.
LLAMA_GGUF = HOME / "models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

# The sampling zend uses for every passthrough turn (zend/src/coding_sampling.rs): vLLM is given
# the same so the comparison is engine against engine. zend ignores these fields on passthrough.
SAMPLING = {"temperature": 0.7, "top_p": 0.95,
            "extra_body": {"top_k": 20, "repetition_penalty": 1.05}}
STEP_LIMIT = 75          # same for both; mini's default is 250
MAX_TOKENS = 16384       # per model call, reasoning included


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def http_ok(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300, r.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001 - any failure means "not up"
        return False, str(e)


def powershell(script, *args):
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           f"{WIN_BENCH}\\{script}", *args]
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


# ── backends ────────────────────────────────────────────────────────────────

def stop_zend():
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    r"$f='D:\candle-work\logs\zend.pid'; if (Test-Path $f) { Stop-Process -Id (Get-Content $f) -Force -ErrorAction SilentlyContinue; Remove-Item $f }"],
                   capture_output=True)


def start_zend(run_dir, zend_env=()):
    """Launch start-zend.ps1 on Windows and poll zend's status from here.

    The script is not waited on: zend, started from it with Start-Process, inherits the
    interop pipes, so the PowerShell process's output never reaches end-of-file while zend
    runs. Its own transcript goes to zend-start.log instead.
    """
    log("starting zend on Windows (standalone, passthrough)" + (f" with {' '.join(zend_env)}" if zend_env else ""))
    # Environment for the zend process: set in the PowerShell session that launches it.
    env_ps = "".join(f"$env:{k}='{v}'; " for k, v in (e.split("=", 1) for e in zend_env))
    win_log = f"{WIN_BENCH}\\runs\\{run_dir.name}\\zend-start.log"
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                      f"Start-Transcript -Path '{win_log}' -Force | Out-Null; {env_ps}"
                      f"& '{WIN_BENCH}\\start-zend.ps1'; Stop-Transcript | Out-Null"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 2400:
        time.sleep(15)
        ok, body = http_ok(f"{ZEND_URL}/v1/status")
        if ok and '"state":"ready"' in body.replace(" ", ""):
            log(f"zend ready after {time.time()-t0:.0f}s")
            time.sleep(30)   # let start-zend.ps1 finish its two smoke turns before the agents start
            return ZEND_URL
        log(f"waiting for zend ({time.time()-t0:.0f}s): {'loading' if ok else 'not answering yet'}")
    raise RuntimeError(f"zend not ready after 40 minutes - see {run_dir/'zend-start.log'}")


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


def start_vllm(run_dir, offloads, max_len):
    for off in offloads:
        args = [str(VLLM), "serve", VLLM_MODEL, "--served-model-name", "passthrough",
                "--host", "127.0.0.1", "--port", "8000",
                "--max-model-len", str(max_len), "--gpu-memory-utilization", "0.90",
                "--max-num-seqs", "8", "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder",
                "--reasoning-parser", "qwen3", "--limit-mm-per-prompt", '{"image":0,"video":0}']
        if off:
            args += ["--cpu-offload-gb", str(off)]
        vlog = run_dir / f"vllm-offload{off}.log"
        log(f"starting vLLM (cpu-offload-gb={off}, max-model-len={max_len}) -> {vlog.name}")
        # WSL appends the Windows PATH, which holds the Windows CUDA toolkit's nvcc; torch's compiler
        # finds it and fails trying to run it. vLLM gets a Linux-only PATH.
        env = dict(os.environ, PATH=":".join(p for p in os.environ["PATH"].split(":") if not p.startswith("/mnt/")))
        # vLLM turns pinned (page-locked) host memory off under WSL2, so offloaded weights stay plain
        # CPU tensors the GPU kernels cannot address. This documented switch turns it back on.
        env["VLLM_WSL2_ENABLE_PIN_MEMORY"] = "1"
        # FlashInfer compiles some kernels (the sampler) on first use: give it the Linux CUDA toolkit.
        if Path("/usr/local/cuda/bin/nvcc").exists():
            env["CUDA_HOME"] = "/usr/local/cuda"
            env["PATH"] = "/usr/local/cuda/bin:" + env["PATH"]
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


# ── measurement helpers ─────────────────────────────────────────────────────

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
    """One tool-offering request through the proxy, exactly as the agent sends it (via litellm).
    Fails the run in seconds instead of letting every task retry for minutes."""
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
    """llama.cpp's server on the identical GGUF. --n-cpu-moe keeps that many layers' experts in RAM
    (computed on the CPU); the rest of the model is on the GPU. Tries each value until one starts."""
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


def task_ids(n):
    """Every 10th SWE-bench Lite test instance (30 in all, across all 12 repos), first n of them."""
    cache = BENCH / "instances.txt"
    if not cache.exists():
        from datasets import load_dataset
        ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        cache.write_text("\n".join(ds[i]["instance_id"] for i in range(0, len(ds), 10)) + "\n")
    return cache.read_text().split()[:n]


def overlay(path, max_tokens, repetition_penalty=None, backend="zend"):
    import yaml
    sampling = json.loads(json.dumps(SAMPLING))
    if repetition_penalty is not None:
        sampling["extra_body"]["repetition_penalty"] = repetition_penalty
    if backend == "llama":
        # llama.cpp names it repeat_penalty and applies it over the last 64 tokens: the windowed kind,
        # like zend's, not vLLM's whole-conversation kind.
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


def score(run_dir, ids):
    """Score preds.json with the SWE-bench harness (its current dataset, which carries each
    instance's image and eval script) and return the counts, or None."""
    preds = run_dir / "agent" / "preds.json"
    if not preds.exists():
        return None
    log("scoring with the SWE-bench harness")
    run_id = run_dir.name
    with open(run_dir / "eval.log", "w") as f:
        subprocess.run([str(AGENT_BIN / "python"), "-m", "swebench.harness.run_evaluation",
                        "--dataset_name", "SWE-bench/SWE-bench_Lite", "--split", "test",
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
    s["score"] = score(run_dir, ids)
    (run_dir / "summary.json").write_text(json.dumps(s, indent=1))
    subprocess.run([str(AGENT_BIN / "python"), str(HERE / "summarize.py"), str(run_dir)])


def stop_backend(backend):
    {"zend": stop_zend, "vllm": stop_vllm, "llama": stop_llama}[backend]()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["zend", "vllm", "llama"])
    ap.add_argument("--cpu-moe", default="8,12,16,20", help="llama.cpp --n-cpu-moe values to try, in order")
    ap.add_argument("--tasks", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--label", default="run")
    ap.add_argument("--offloads", default="6,8,10,12,14", help="vLLM --cpu-offload-gb values to try, in order")
    ap.add_argument("--max-model-len", type=int, default=65536)
    ap.add_argument("--keep-backend", action="store_true", help="leave the server running afterwards")
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--rescore", metavar="RUN_DIR", help="only (re)score an existing run")
    ap.add_argument("--repetition-penalty", type=float,
                    help="override the repetition penalty sent to the backend (vLLM honours it; zend ignores it)")
    ap.add_argument("--tasks-file", help="run exactly these instance ids (one per line) instead of the standard list")
    ap.add_argument("--fresh-context", action="store_true",
                    help="proxy makes every call a new conversation (tests zend without its held context)")
    ap.add_argument("--zend-env", action="append", default=[], metavar="KEY=VALUE",
                    help="environment variable for the zend process (repeatable), e.g. ZEND_PT_SUPPRESS_PENALTY=0")
    a = ap.parse_args()
    if a.rescore:
        rescore(Path(a.rescore).resolve())
        return

    ids = Path(a.tasks_file).read_text().split() if a.tasks_file else task_ids(a.tasks)
    run_dir = BENCH / "runs" / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{a.label}_{a.backend}_w{a.workers}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks.txt").write_text("\n".join(ids) + "\n")
    log(f"{a.backend}: {len(ids)} tasks, {a.workers} parallel agents -> {run_dir}")

    stop_vllm(); stop_llama(); stop_zend(); time.sleep(5)
    if a.backend == "zend":
        if a.zend_env:
            (run_dir / "zend-env.txt").write_text("\n".join(a.zend_env) + "\n")
        upstream = start_zend(run_dir, a.zend_env)
    elif a.backend == "vllm":
        upstream = start_vllm(run_dir, [int(x) for x in a.offloads.split(",")], a.max_model_len)
    else:
        upstream = start_llama(run_dir, [int(x) for x in a.cpu_moe.split(",")], a.max_model_len, max(a.workers, 1))

    proxy = subprocess.Popen([str(AGENT_BIN / "python"), str(HERE / "proxy.py"), "--listen", str(PROXY_PORT),
                              "--upstream", upstream, "--log", str(run_dir / "calls.jsonl")]
                             + (["--fresh-context"] if a.fresh_context else []))
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
    overlay(run_dir / "overlay.yaml", MAX_TOKENS, a.repetition_penalty, a.backend)
    filt = "^(" + "|".join(re.escape(i) for i in ids) + ")$"
    env = dict(os.environ, MSWEA_COST_TRACKING="ignore_errors", MSWEA_SILENT_STARTUP="1")
    agent_cmd = [str(AGENT_BIN / "mini-extra"), "swebench", "--subset", "lite", "--split", "test",
                 "--filter", filt, "-w", str(a.workers), "-o", str(run_dir / "agent"),
                 "-c", "swebench.yaml", "-c", str(run_dir / "overlay.yaml"), "--environment-class", "docker", "--redo-existing"]
    log("agents running")
    t0 = time.time()
    with open(run_dir / "agent.log", "w") as f:
        agent = subprocess.Popen(agent_cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
        while agent.poll() is None:
            time.sleep(30)
            # zend writes every conversation to its substrate on D:; stop rather than fill the disk.
            free_gb = shutil.disk_usage("/mnt/d").free / 2**30
            if free_gb < 40:
                log(f"D: has {free_gb:.0f} GB free - stopping the agents to protect the disk")
                agent.terminate()
                agent.wait(120)
                break
        rc = agent.returncode
    wall = time.time() - t0
    log(f"agents finished: exit {rc}, {wall/60:.1f} min")
    stop.set(); proxy.terminate()
    if not a.keep_backend:
        stop_backend(a.backend)

    resolved = None if a.no_eval else score(run_dir, ids)

    summary = {"backend": a.backend, "workers": a.workers, "tasks": len(ids), "fresh_context": a.fresh_context, "repetition_penalty": a.repetition_penalty, "wall_seconds": round(wall),
               "agent_exit": rc, "score": resolved}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    log(f"summary: {json.dumps(summary)}")
    subprocess.run([str(AGENT_BIN / "python"), str(HERE / "summarize.py"), str(run_dir)])


if __name__ == "__main__":
    main()
