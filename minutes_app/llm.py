import http.client
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import guard
from .config import env

OPENAI_COMPATIBLE = {
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
    "openai": ("OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", True),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", True),
    "xai": ("Grok (xAI)", "https://api.x.ai/v1", "XAI_API_KEY", True),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", True),
    "huggingface": ("Hugging Face", "https://router.huggingface.co/v1", "HF_TOKEN", True),
    "lmstudio": ("LM Studio (local)", "http://localhost:1234/v1", "", False),
    "ollama": ("Ollama (local)", "http://localhost:11434/v1", "", False),
    "custom": ("OpenAI-compatible server", "", "CUSTOM_LLM_API_KEY", False),
}
ANTHROPIC = ("Claude (Anthropic API key)", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", True)


MAX_RESPONSE = 20 * 1024 * 1024


class LLMError(Exception):
    pass


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _pinned_post(url, address, headers, payload, timeout):
    parts = urllib.parse.urlsplit(url)
    conn = _PinnedHTTPS(parts.hostname, parts.port or 443, address, timeout)
    try:
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        conn.request("POST", path, body=payload, headers=dict(headers, **{"Content-Type": "application/json"}))
        resp = conn.getresponse()
        raw = resp.read(MAX_RESPONSE + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise LLMError("could not reach %s (%s)" % (parts.hostname, exc))
    finally:
        conn.close()
    if len(raw) > MAX_RESPONSE:
        raise LLMError("the AI response from %s was too large" % parts.hostname)
    if resp.status >= 300:
        raise LLMError("HTTP %s from %s: %s" % (resp.status, parts.hostname, raw.decode("utf-8", "replace")[:500]))
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise LLMError("the AI server at %s did not return JSON" % parts.hostname)


def providers():
    rows = []
    for name, (label, base, key_var, needs_key) in OPENAI_COMPATIBLE.items():
        if name == "custom":
            base = env("CUSTOM_LLM_BASE_URL")
        rows.append({"id": name, "label": label, "base": base, "key_var": key_var,
                     "ready": bool(base) and (not needs_key or bool(env(key_var)))})
    label, base, key_var, _ = ANTHROPIC
    rows.append({"id": "anthropic", "label": label, "base": base, "key_var": key_var,
                 "ready": bool(env(key_var))})
    return rows


def missing_key(label, key_var, use_env):
    if use_env:
        return "no API key for %s: set %s in .env" % (label, key_var)
    return "no API key for %s: add one to this AI connection in Settings" % label


def _post(url, headers, body, timeout=300, guard=None):
    try:
        address = guard(url) if guard else None
    except ValueError as exc:
        raise LLMError(str(exc))
    if address:
        return _pinned_post(url, address, headers, json.dumps(body).encode("utf-8"), timeout)
    if not url.lower().startswith(("http://", "https://")):
        raise LLMError("AI server URLs must start with http:// or https://")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError("HTTP %s from %s: %s" % (exc.code, url, exc.read().decode("utf-8", "replace")[:500]))
    except urllib.error.URLError as exc:
        raise LLMError("could not reach %s (%s). Is the server running?" % (url, exc.reason))


def _meter(creds, data, inp, out):
    meter = creds.get("meter")
    if meter is None:
        return
    usage = (data or {}).get("usage") or {}
    meter({"input_tokens": int(usage.get(inp) or 0), "output_tokens": int(usage.get(out) or 0)})


def _stream(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.strip()
                if line:
                    yield json.loads(line.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError("HTTP %s from the free AI: %s" % (exc.code, exc.read().decode("utf-8", "replace")[:300]))
    except urllib.error.URLError as exc:
        raise LLMError("could not reach the free AI (%s)" % exc.reason)


def _builtin(model, system, user, max_tokens, creds):
    base = (creds.get("base_url") or "").rstrip("/")
    if not base:
        raise LLMError("the free AI is not set up on this server")
    context = int(creds.get("context") or 32768)
    estimate = (len(system) + len(user)) // 3 + max_tokens
    if estimate > context:
        raise LLMError("this is too long for the free AI (about %d words); choose another AI under Settings, AI"
                       % (len(user.split())))
    progress = creds.get("progress") or (lambda *a, **k: None)
    progress("reading", len(system) + len(user))
    body = {"model": model, "stream": True, "think": False, "keep_alive": "15m",
            "options": {"num_ctx": context, "num_predict": max_tokens, "temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if creds.get("json", True):
        body["format"] = "json"
    parts, count, final = [], 0, {}
    for chunk in _stream(base + "/api/chat", body, int(creds.get("timeout") or 300)):
        if chunk.get("error"):
            raise LLMError("the free AI stopped: %s" % str(chunk["error"])[:300])
        piece = (chunk.get("message") or {}).get("content") or ""
        if piece:
            parts.append(piece)
            count += 1
            progress("writing", count)
        if chunk.get("done"):
            final = chunk
    progress("done", int(final.get("eval_count") or count), final)
    meter = creds.get("meter")
    if meter is not None:
        meter({"input_tokens": int(final.get("prompt_eval_count") or 0), "output_tokens": int(final.get("eval_count") or count)})
    return guard.output("".join(parts))


def complete(provider, model, system, user, max_tokens=4096, creds=None):
    use_env = creds is None
    creds = creds or {}
    system, user = guard.clean(system, 60000), guard.clean(user, 400000)
    if creds.get("before"):
        creds["before"]()
    if not model:
        raise LLMError("choose a model for " + provider)
    if provider == "builtin":
        return _builtin(model, system, user, max_tokens, creds)
    if provider == "anthropic":
        label, base, key_var, _ = ANTHROPIC
        base = creds.get("base_url") or base
        key = creds.get("api_key") or (env(key_var) if use_env else "")
        if not key:
            raise LLMError(missing_key(label, key_var, use_env))
        blocks = [{"type": "text", "text": system}]
        if len(system) > 4000:
            blocks[0]["cache_control"] = {"type": "ephemeral"}
        data = _post(base + "/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": max_tokens, "system": blocks,
                      "messages": [{"role": "user", "content": user}]}, guard=creds.get("guard"))
        _meter(creds, data, "input_tokens", "output_tokens")
        return guard.output("".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"))

    if provider not in OPENAI_COMPATIBLE:
        raise LLMError("unknown provider " + repr(provider))
    label, base, key_var, needs_key = OPENAI_COMPATIBLE[provider]
    if provider == "custom" and use_env:
        base = env("CUSTOM_LLM_BASE_URL")
    base = creds.get("base_url") or base
    if not base:
        raise LLMError("no server URL for " + label)
    key = creds.get("api_key") or (env(key_var) if key_var and use_env else "")
    if needs_key and not key:
        raise LLMError(missing_key(label, key_var, use_env))
    headers = {"Authorization": "Bearer " + key} if key else {}
    if provider == "openrouter":
        headers["X-Title"] = "Live Minutes"
    data = _post(base.rstrip("/") + "/chat/completions", headers,
                 {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]}, guard=creds.get("guard"))
    _meter(creds, data, "prompt_tokens", "completion_tokens")
    try:
        return guard.output(data["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        raise LLMError("unexpected response shape: " + json.dumps(data)[:300])


def extract_json(text):
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        if start < 0:
            raise LLMError("the model did not return JSON")
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        raise LLMError("the model's JSON was cut off (try a larger max_tokens or model)")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError("the model returned invalid JSON: %s" % exc)
