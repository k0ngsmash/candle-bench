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


def start_zend(run_dir):
    """Launch start-zend.ps1 on Windows and poll zend's status from here.

    The script is not waited on: zend, started from it with Start-Process, inherits the
    interop pipes, so the PowerShell process's output never reaches end-of-file while zend
    runs. Its own transcript goes to zend-start.log instead.
    """
    log("starting zend on Windows (standalone, passthrough)")
    win_log = f"{WIN_BENCH}\\runs\\{run_dir.name}\\zend-start.log"
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                      f"Start-Transcript -Path '{win_log}' -Force | Out-Null; "
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


def task_ids(n):
    """Every 10th SWE-bench Lite test instance (30 in all, across all 12 repos), first n of them."""
    cache = BENCH / "instances.txt"
    if not cache.exists():
        from datasets import load_dataset
        ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        cache.write_text("\n".join(ds[i]["instance_id"] for i in range(0, len(ds), 10)) + "\n")
    return cache.read_text().split()[:n]


def overlay(path, max_tokens):
    import yaml
    cfg = {
        "agent": {"step_limit": STEP_LIMIT, "cost_limit": 0},
        "model": {
            "model_name": "openai/passthrough",
            "model_kwargs": {"api_base": f"http://127.0.0.1:{PROXY_PORT}/v1", "api_key": "none",
                             "timeout": 3600, "max_tokens": max_tokens, **SAMPLING},
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["zend", "vllm"])
    ap.add_argument("--tasks", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--label", default="run")
    ap.add_argument("--offloads", default="6,8,10,12,14", help="vLLM --cpu-offload-gb values to try, in order")
    ap.add_argument("--max-model-len", type=int, default=65536)
    ap.add_argument("--keep-backend", action="store_true", help="leave the server running afterwards")
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--rescore", metavar="RUN_DIR", help="only (re)score an existing run")
    a = ap.parse_args()
    if a.rescore:
        rescore(Path(a.rescore).resolve())
        return

    ids = task_ids(a.tasks)
    run_dir = BENCH / "runs" / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{a.label}_{a.backend}_w{a.workers}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks.txt").write_text("\n".join(ids) + "\n")
    log(f"{a.backend}: {len(ids)} tasks, {a.workers} parallel agents -> {run_dir}")

    stop_vllm(); stop_zend(); time.sleep(5)
    upstream = start_zend(run_dir) if a.backend == "zend" else start_vllm(run_dir, [int(x) for x in a.offloads.split(",")], a.max_model_len)

    proxy = subprocess.Popen([str(AGENT_BIN / "python"), str(HERE / "proxy.py"), "--listen", str(PROXY_PORT),
                              "--upstream", upstream, "--log", str(run_dir / "calls.jsonl")])
    time.sleep(3)
    stop = threading.Event()
    sampler = threading.Thread(target=gpu_sampler, args=(run_dir / "gpu.csv", stop), daemon=True)
    sampler.start()

    try:
        preflight_call(run_dir)
    except RuntimeError as e:
        log(str(e))
        stop.set(); proxy.terminate()
        stop_vllm() if a.backend == "vllm" else stop_zend()
        sys.exit(1)
    overlay(run_dir / "overlay.yaml", MAX_TOKENS)
    filt = "^(" + "|".join(re.escape(i) for i in ids) + ")$"
    env = dict(os.environ, MSWEA_COST_TRACKING="ignore_errors", MSWEA_SILENT_STARTUP="1")
    agent_cmd = [str(AGENT_BIN / "mini-extra"), "swebench", "--subset", "lite", "--split", "test",
                 "--filter", filt, "-w", str(a.workers), "-o", str(run_dir / "agent"),
                 "-c", "swebench.yaml", "-c", str(run_dir / "overlay.yaml"), "--environment-class", "docker", "--redo-existing"]
    log("agents running")
    t0 = time.time()
    with open(run_dir / "agent.log", "w") as f:
        rc = subprocess.run(agent_cmd, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    wall = time.time() - t0
    log(f"agents finished: exit {rc}, {wall/60:.1f} min")
    stop.set(); proxy.terminate()
    if not a.keep_backend:
        stop_vllm() if a.backend == "vllm" else stop_zend()

    resolved = None if a.no_eval else score(run_dir, ids)

    summary = {"backend": a.backend, "workers": a.workers, "tasks": len(ids), "wall_seconds": round(wall),
               "agent_exit": rc, "score": resolved}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    log(f"summary: {json.dumps(summary)}")
    subprocess.run([str(AGENT_BIN / "python"), str(HERE / "summarize.py"), str(run_dir)])


if __name__ == "__main__":
    main()
