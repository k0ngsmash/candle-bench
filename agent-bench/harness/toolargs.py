"""Repair tool-call argument strings that are almost-JSON.

gpt-oss (harmony format behind vLLM's chat-completions tool parser) emits long bash commands whose
argument string is not valid JSON: raw newlines/tabs inside the string, or unescaped double quotes
inside a heredoc / python -c body. The agent harness then rejects the call and, after a few in a row,
abandons the task - so the run measures the parser, not the agent. This module turns such strings
back into the JSON the model evidently meant, conservatively, and says what it did.

repair(args, required_key="command") -> (fixed_json_str | None, how)
  how is one of: "ok" (already valid), "strict-off" (raw control chars only), "shape" (recovered the
  single required string field from a {"<key>": "..."} shape), or "fail" (left alone).
Only the {"<key>": "<string>"} shape is reconstructed; anything else is returned unchanged.
"""
import json
import re

_SHAPE = re.compile(r'^\s*\{\s*"(?P<key>[A-Za-z_]\w*)"\s*:\s*"(?P<val>.*)"\s*\}\s*$', re.S)


def repair(args, required_key="command"):
    if not isinstance(args, str):
        return None, "fail"
    try:
        json.loads(args)
        return None, "ok"
    except ValueError:
        pass
    try:
        obj = json.loads(args, strict=False)            # tolerates raw control chars inside strings
        if isinstance(obj, dict) and required_key in obj:
            return json.dumps(obj), "strict-off"
    except ValueError:
        pass
    m = _SHAPE.match(args)
    if m and m.group("key") == required_key:
        raw = m.group("val")
        # decode the escapes the model did write (\n, \", \\, \t, \uXXXX) and keep everything else literal
        val = re.sub(r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})',
                     lambda e: json.loads('"\\' + e.group(1) + '"'), raw)
        return json.dumps({required_key: val}), "shape"
    return None, "fail"
