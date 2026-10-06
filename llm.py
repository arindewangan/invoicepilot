"""Provider-agnostic LLM client for InvoicePilot.

Uses any OpenAI-compatible chat-completions API, configured purely by env vars:
    LLM_API_KEY    - API key (required for real AI)
    LLM_BASE_URL   - e.g. https://api.openai.com/v1 (default)
    LLM_MODEL      - e.g. gpt-4o-mini (default)

When no key is set, callers must fall back to a clearly-labelled
rule-based demo mode. No credentials are ever invented.
"""
import json
import os

import requests

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


def llm_configured() -> bool:
    """True when a real LLM can be called."""
    return bool(os.environ.get("LLM_API_KEY"))


def llm_label() -> str:
    if llm_configured():
        return os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    return "rule-based demo mode"


def chat_complete(system: str, user: str, json_mode: bool = True, timeout: int = 30):
    """Call the configured chat-completions endpoint.

    Returns the parsed JSON dict (or raw text when json_mode=False),
    or None if anything fails (caller should fall back to demo rules).
    """
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content) if json_mode else content
    except Exception:
        return None
