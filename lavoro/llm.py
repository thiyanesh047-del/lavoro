"""Calling Claude for structured answers. Two backends:

  claude_cli  (default) — runs the `claude` command (Claude Code) you are already logged into with your Claude plan.
                No API key, no per-token bill; it counts toward your plan's usage limits instead.
  api         — the Anthropic API with ANTHROPIC_API_KEY (billed per token).

Both return a validated Pydantic object, or None if Claude declined or returned nothing usable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import warnings
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_cfg: dict = {}
_stop = threading.Event()   # set when the plan's usage limit is hit, so we stop calling


def configure(cfg: dict) -> None:
    global _cfg
    _cfg = cfg.get("llm", {}) or {}


def backend() -> str | None:
    """Which backend is usable right now: 'claude_cli', 'api' or None."""
    want = _cfg.get("backend", "claude_cli")
    if want == "claude_cli" and shutil.which("claude"):
        return "claude_cli"
    if want == "api" and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "api"
    return None


def describe() -> str:
    b = backend()
    if b == "claude_cli":
        return f"Claude Code CLI on your Claude plan (model: {_cfg.get('cli_model') or 'your default'})"
    if b == "api":
        return f"Anthropic API (model: {_cfg.get('model', 'claude-opus-5-5')})"
    want = _cfg.get("backend", "claude_cli")
    return ("no Claude: the `claude` command was not found on PATH" if want == "claude_cli"
            else "no Claude: ANTHROPIC_API_KEY is not set")


def parse(*, effort: str, system: str, user: str, schema: type[T], web: bool | str = False, max_tokens: int = 16000,
          pdf: str | None = None) -> T | None:
    """`pdf`: path to a PDF Claude should read (a CV). The CLI reads it with its Read tool; the API gets it inline.
    `web`: True = web search and page fetching; "search" = web search only (results and snippets, no page opened)."""
    if _stop.is_set():
        return None
    b = backend()
    if b == "claude_cli":
        return _cli(effort=effort, system=system, user=user, schema=schema, web=web, pdf=pdf)
    if b == "api":
        return _api(effort=effort, system=system, user=user, schema=schema, web=web, max_tokens=max_tokens, pdf=pdf)
    raise RuntimeError(describe())


# ---------------------------------------------------------------- Claude Code CLI (plan)
def _strict(schema: dict) -> dict:
    """Pydantic JSON schema → strict schema (no extra keys, every field required, no 'title' metadata)."""
    if not isinstance(schema, dict):
        return schema
    if isinstance(schema.get("title"), str):
        schema.pop("title")  # metadata only; a *property* named title lives under "properties"
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"])
        for sub in schema["properties"].values():
            _strict(sub)
    for key in ("items", "$defs", "anyOf", "allOf"):
        v = schema.get(key)
        if isinstance(v, dict):
            for sub in (v.values() if key == "$defs" else [v]):
                _strict(sub)
        elif isinstance(v, list):
            for sub in v:
                _strict(sub)
    return schema


# LinkedIn does not allow automated reading of its pages, so Claude may see LinkedIn search results but never open them.
NO_FETCH = ["WebFetch(domain:linkedin.com)", "WebFetch(domain:www.linkedin.com)", "WebFetch(domain:se.linkedin.com)"]


def _cli(*, effort: str, system: str, user: str, schema: type[T], web: bool | str, pdf: str | None = None) -> T | None:
    tools = "WebSearch" if web == "search" else "WebSearch,WebFetch" if web else ("Read" if pdf else "")
    cmd = [
        shutil.which("claude"), "-p",
        "--output-format", "json",
        "--no-session-persistence",
        # Keep each call small: no plugins, skills, MCP servers, hooks or project settings get loaded.
        "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "",
        "--system-prompt", "You are a careful assistant inside a personal job-search tool. "
                           "Follow the instructions in the user message and answer only through the structured output.",
        "--json-schema", json.dumps(_strict(schema.model_json_schema())),
        "--tools", tools,
    ]
    if web:
        cmd += ["--allowedTools", tools, "--disallowedTools", *NO_FETCH, "--max-turns", "12"]
    elif pdf:
        cmd += ["--allowedTools", "Read", "--max-turns", "8"]
    if _cfg.get("cli_model"):
        cmd += ["--model", _cfg["cli_model"]]
    if effort:
        cmd += ["--effort", effort]
    if pdf:
        user = "First read the attached CV with the Read tool: ./cv.pdf (in the current folder).\n\n" + user
    prompt = f"<instructions>\n{system}\n</instructions>\n\n{user}"
    # Run from an empty folder so no CLAUDE.md or project files are picked up.
    with tempfile.TemporaryDirectory() as cwd:
        if pdf:
            shutil.copyfile(pdf, os.path.join(cwd, "cv.pdf"))
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                               cwd=cwd, timeout=600 if web else 240)
        except subprocess.TimeoutExpired:
            raise RuntimeError("claude CLI timed out")  # a failure, not an answer: callers retry later
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude CLI gave no JSON (exit {p.returncode}): {(p.stderr or p.stdout)[:300]}")
    if out.get("is_error"):
        msg = str(out.get("result") or out.get("api_error_status") or "")
        if any(w in msg.lower() for w in ("limit", "usage", "quota", "rate")):
            _stop.set()
            print(f"  ! Claude plan limit reached, stopping AI steps for this run: {msg[:200]}")
            return None
        # Any other error is a failure, not a refusal: raise, so a job is retried instead of being scored 0.
        raise RuntimeError(f"claude CLI error: {msg[:300] or 'no message'}")
    data = out.get("structured_output")
    if data is None:
        return None
    try:
        return schema.model_validate(data)
    except Exception as e:
        print(f"  ! unexpected answer shape: {e}")
        return None


# ---------------------------------------------------------------- Anthropic API (pay per token)
_client = None
_fallbacks_ok = True


def _api(*, effort: str, system: str, user: str, schema: type[T], web: bool, max_tokens: int,
         pdf: str | None = None) -> T | None:
    global _client, _fallbacks_ok
    import base64

    import anthropic

    # The beta parse helper still accepts a Pydantic class via output_format (it builds the strict
    # JSON schema and validates the reply); it only warns that the parameter name is deprecated.
    warnings.filterwarnings("ignore", message="The 'output_format' parameter is deprecated")
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    content: list | str = user
    if pdf:
        with open(pdf, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        content = [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
                   {"type": "text", "text": user}]
    messages: list = [{"role": "user", "content": content}]
    kw = dict(model=_cfg.get("model", "claude-opus-5-5"), max_tokens=max_tokens, system=system,
              output_config={"effort": effort}, output_format=schema)
    if web:
        kw["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    for _ in range(4):  # server tools may pause a long turn; resume it
        resp = None
        if _fallbacks_ok:
            try:
                # On a safety decline the API re-runs the request on a fallback model automatically.
                resp = _client.beta.messages.parse(
                    messages=messages, betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                _fallbacks_ok = False
        if resp is None:
            resp = _client.messages.parse(messages=messages, **kw)
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            continue
        if resp.stop_reason == "refusal":
            return None
        return resp.parsed_output
    return None
