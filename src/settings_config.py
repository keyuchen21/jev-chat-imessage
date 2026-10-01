"""Settings editor and explicit network probes; never mutates running credentials."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import re
import shlex
import socket
import ssl
import tempfile
import urllib.error
import urllib.parse

import userconfig
from chat_context import message_limit
from generate import _endpoint, base_is_verbatim_action, http_post_json, jev_request_url, Generator, ThinkingOnlyError
import styles

PREFIXES = ("TYPESAFE", "OPENAI", "ANTHROPIC")
FIELDS = ("API_KEY", "BASE_URL", "MODEL")
DEFAULTS = {
    "TYPESAFE": ("https://api.typesafe.ai", "jev-latest"),
    "OPENAI": ("https://api.openai.com/v1", ""),
    "ANTHROPIC": ("https://api.anthropic.com", ""),
}
ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z_0-9]*)(\s*=\s*)(.*)$")


def read_document(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def write_settings(path: Path, original: str, changes: dict[str, str]) -> str:
    """Change only edited assignments, preserve other lines, replace atomically at 0600."""
    if read_document(path) != original:
        raise ValueError("Another program changed the config file. Close Settings and open it again.")
    # JUDGE_BACKEND is the first-run dialog's choice (judge.download_block_reason);
    # the settings window's offline-model section writes it through the same guarded path.
    allowed = {f"{p}_{f}" for p in PREFIXES for f in FIELDS} | {
        "JUDGE_BACKEND", "JEV_HISTORY", "JEV_CONTEXT_MESSAGES",
        "JEV_MESSAGE_REGION", "JEV_INPUT_REGION", "JEV_CANDIDATES_PER_TONE",
        "JEV_REPLY_LANGUAGE"}
    if not changes.keys() <= allowed:
        raise ValueError("Unsupported setting.")
    for value in changes.values():
        if any(c in value for c in "\r\n\0"):
            raise ValueError("Values cannot contain line breaks or null characters.")
    if "JEV_CONTEXT_MESSAGES" in changes:
        message_limit(changes["JEV_CONTEXT_MESSAGES"])
    if "JEV_HISTORY" in changes and changes["JEV_HISTORY"] not in ("0", "1"):
        raise ValueError("The history switch must be 0 or 1")
    if "JEV_CANDIDATES_PER_TONE" in changes:
        styles.validate_candidate_count(changes["JEV_CANDIDATES_PER_TONE"])
    if "JEV_REPLY_LANGUAGE" in changes:
        styles.validate_reply_language(changes["JEV_REPLY_LANGUAGE"])
    remaining = dict(changes)
    lines = []
    for line in original.splitlines(keepends=True):
        match = ASSIGNMENT.match(line.rstrip("\r\n"))
        if match and match[2] in changes:
            key = match[2]
            # Keep even duplicate assignments consistent, so shell and Python agree.
            _, comment = userconfig.split_env_comment(match[4])
            ending = "\n" if line.endswith("\n") else ""
            line = f"{match[1]}{key}{match[3]}{shlex.quote(changes[key])}"
            line += (" " + comment if comment else "") + ending
            remaining.pop(key, None)
        lines.append(line)
    text = "".join(lines)
    if remaining:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "".join(f"export {k}={shlex.quote(v)}\n" for k, v in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return text


def validate_endpoint(base: str) -> str:
    base = base.strip().rstrip("/")
    p = urllib.parse.urlsplit(base)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("The base URL must be an http(s) URL without a username, password, query or fragment.")
    return base


def list_models(prefix: str, base: str, key: str) -> list[str]:
    """GET the provider's models endpoint. No presets, redirects or alternate service."""
    base = validate_endpoint(base)
    if not key:
        raise ValueError("Enter an API key first (for Ollama, enter ollama).")
    if prefix == "TYPESAFE" and base_is_verbatim_action(base):
        # A complete action path (e.g. Vercel …/v1/evaluate) has no sibling /models we
        # can derive — appending anything would just 404 on the action itself.
        raise ValueError("This URL is a full action path, so no model list is available. Enter the model name manually.")
    api = "anthropic" if prefix == "ANTHROPIC" else "openai"
    url = _endpoint(base, api).rsplit("/", 1)[0]
    if api == "openai":
        url = url.removesuffix("/chat")
    url += "/models"
    headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"}
               if api == "anthropic" else {"authorization": f"Bearer {key}"})
    offered = []
    after = None
    while True:
        p = urllib.parse.urlsplit(url)
        path = p.path + ("?after_id=" + urllib.parse.quote(after, safe="") if after else "")
        cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
        assert p.hostname is not None  # validate_endpoint checked the host above.
        conn = cls(p.hostname, p.port, timeout=15)
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            if resp.status >= 300:
                raise urllib.error.HTTPError(url, resp.status, "", resp.headers, None)
            data = json.loads(resp.read())
        finally:
            conn.close()
        # TypeSafe documents {models: [{name, description, release_date}]};
        # OpenAI/Anthropic use {data: [{id, ...}]}. Do not guess alternate schemas.
        collection, field = ("models", "name") if prefix == "TYPESAFE" else ("data", "id")
        offered.extend(m[field] for m in data.get(collection, [])
                       if isinstance(m, dict) and isinstance(m.get(field), str) and m[field])
        if api != "anthropic" or not data.get("has_more"):
            break
        next_id = data.get("last_id")
        if not next_id or next_id == after:
            raise ValueError("The model list came back with bad paging. Enter the model manually.")
        after = next_id
    if not offered:
        raise ValueError("The service returned no model list. Enter the model manually.")
    return sorted(set(offered))


def test_connection(prefix: str, base: str, key: str, model: str, extra: dict | None = None) -> None:
    """Use exactly the unsaved form values; never fall back to built-in credentials."""
    base = validate_endpoint(base)
    if not key or not model.strip():
        raise ValueError("Enter an API key and a model, then test.")
    if prefix == "TYPESAFE":
        # Same endpoint/transport as JevJudge — through the SAME composition rule, so a
        # base that tests well here cannot 404 at run time (…/v1, Vercel verbatim, …).
        body = {"model": model, "state": "Hello", "questions": {
            "test": {"type": "choice", "instructions": "Pick the greeting", "criteria": {"greeting": None}}}}
        data = http_post_json(jev_request_url(base), {
            "content-type": "application/json", "authorization": f"Bearer {key}"}, body, 30)
        if ((data.get("answers") or {}).get("test") or {}).get("choice") != "greeting":
            raise ValueError("The service answered, but with no valid judgment result.")
        return
    api = "anthropic" if prefix == "ANTHROPIC" else "openai"
    body = {"model": model, "max_tokens": 300, "temperature": 0.9,
            "messages": [{"role": "user", "content": "Reply with exactly: connected"}]}
    headers = {"content-type": "application/json"}
    if api == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        body.update(extra or {})
        # Testing must exercise the model the user selected, not an extra-body override.
        body.update(model=model, stream=False)
        headers["authorization"] = f"Bearer {key}"
    data = http_post_json(_endpoint(base, api), headers, body, 30)
    if api == "anthropic":
        raw = "".join(p.get("text", "") for p in data.get("content", []) if isinstance(p, dict))
    else:
        raw = Generator._openai_json(data, model, "non-thinking model")
    if not raw.strip():
        raise ValueError("The service returned no text. Check that the model can generate text, or turn off thinking mode.")


def error_message(error: Exception) -> str:
    """Never display raw remote bodies, URLs or exception strings containing credentials.

    网络类故障按层细分（#116：此前 DNS/拒绝/超时/TLS 全折叠成一句「连接失败或超时」，
    用户无从定位——最常见的是网络环境需要代理，而连接池走 http.client 直连、不读
    系统代理，浏览器可达 ≠ 应用可达）。文案只给类别与可行动提示，绝不回显 URL/密钥。
    """
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}: check the base URL, API key and model access."
    if isinstance(error, ThinkingOnlyError):
        return "The model returned only thinking and no answer. Turn off thinking mode or use another model."
    reason = getattr(error, "reason", error)
    if isinstance(reason, socket.gaierror):
        return "DNS lookup failed: check the spelling of the base URL and this Mac's DNS (a public DNS such as 1.1.1.1 can help you check)."
    if isinstance(reason, ConnectionRefusedError):
        return "Connection refused: the port is closed, or a firewall or security tool on this Mac blocks it."
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return ("Connection timed out (no response in 30 s). Note: the app connects directly and does not use the system proxy. "
                "If your network needs a proxy (company network, proxy tool), a site that works in the browser can still fail here. "
                "Allow a direct connection to this domain, then try again.")
    if isinstance(reason, (ssl.SSLError, ssl.SSLCertVerificationError)):
        return "TLS certificate check failed: make sure the system clock is correct and nothing intercepts the connection."
    if isinstance(error, (TimeoutError, OSError, http.client.HTTPException)):
        return "Connection failed: check the base URL and your network."
    return "The request got no valid result. Check the base URL, the model, and that the service supports this API."
