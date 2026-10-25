"""Transparent logging proxy between the agent and a backend (zend or vLLM).

Forwards every request unchanged and appends one JSON line per completion call:
wall time, status, prompt/completion tokens as the backend reports them, and a
short hash of the opening user message so calls can be grouped per task.
Non-streaming only, which is what mini-swe-agent uses.
"""
import argparse
import hashlib
import json
import time

from aiohttp import ClientSession, ClientTimeout, web


def conversation_tag(body: dict) -> str:
    for m in body.get("messages", []):
        if m.get("role") == "user":
            c = m.get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            return hashlib.sha1(text.encode()).hexdigest()[:10]
    return "-"


async def handle(request: web.Request) -> web.Response:
    app = request.app
    raw = await request.read()
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
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
            "conv": conversation_tag(body), "n_messages": len(body.get("messages", [])),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "finish_reason": finish, "tool_calls": n_calls,
        }
        with open(app["log"], "a") as f:
            f.write(json.dumps(rec) + "\n")
    return web.Response(body=data, status=status, content_type=ctype.split(";")[0])


async def on_startup(app):
    app["session"] = ClientSession(timeout=ClientTimeout(total=3600))


async def on_cleanup(app):
    await app["session"].close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--listen", type=int, required=True)
    p.add_argument("--upstream", required=True, help="e.g. http://127.0.0.1:8090")
    p.add_argument("--log", required=True)
    a = p.parse_args()
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app.update(upstream=a.upstream.rstrip("/"), log=a.log)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{tail:.*}", handle)
    web.run_app(app, host="127.0.0.1", port=a.listen, print=None)


if __name__ == "__main__":
    main()
