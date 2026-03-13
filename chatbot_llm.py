from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


_CRISIS_PATTERNS = [
    re.compile(r"\b(suicide|suicidal)\b", re.IGNORECASE),
    re.compile(r"\b(kill myself|end my life)\b", re.IGNORECASE),
    re.compile(r"\b(self[- ]?harm|cut myself|hurt myself)\b", re.IGNORECASE),
    re.compile(r"\b(i want to die|i dont want to live|i don't want to live)\b", re.IGNORECASE),
]


def crisis_reply_if_needed(message: str) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None

    if not any(pattern.search(text) for pattern in _CRISIS_PATTERNS):
        return None

    return (
        "I'm really sorry you're feeling this way. I can't help with self-harm instructions, "
        "but you deserve support right now.\n\n"
        "If you're in immediate danger, call your local emergency number now.\n"
        "If you're in the US or Canada, you can call or text 988.\n"
        "If you're elsewhere, consider contacting a local crisis hotline or a trusted person nearby.\n\n"
        "If you want, tell me where you are (country) and whether you're safe right now, and I can help you find options."
    )


def is_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _sanitize_history(history: Any, max_items: int = 12, max_chars: int = 500) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []

    sanitized: list[dict[str, str]] = []
    for item in history[-max_items:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = str(item.get("content") or "").strip()
        if not content:
            continue

        sanitized.append({"role": role, "content": content[:max_chars]})

    return sanitized


def _build_system_prompt() -> str:
    return (
        "You are MindGuard Support Assistant, a supportive mental-wellness chatbot.\n"
        "Goals:\n"
        "- Be empathetic, calm, and practical.\n"
        "- Ask 1 gentle clarifying question when needed.\n"
        "- Give short, actionable coping steps (breathing, grounding, planning, sleep hygiene).\n"
        "- Do NOT claim to be a therapist or provide medical diagnosis.\n"
        "- If the user mentions self-harm or suicide, encourage immediate help and crisis resources.\n"
        "- Keep responses under ~120 words unless the user asks for more detail.\n"
    )


def _extract_text(payload: dict[str, Any]) -> str:
    # Chat Completions-style response
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

    # Responses-style response (best-effort)
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    return ""


def generate_reply(user_message: str, history: Any = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    timeout_raw = os.environ.get("OPENAI_TIMEOUT", "15").strip() or "15"
    try:
        timeout = max(3, min(60, int(timeout_raw)))
    except ValueError:
        timeout = 15

    messages: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt()}]
    messages.extend(_sanitize_history(history))
    messages.append({"role": "user", "content": str(user_message or "").strip()})

    request_payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 250,
    }

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode("utf-8", errors="replace")
        except Exception:
            details = ""
        raise RuntimeError(f"LLM request failed: HTTP {exc.code} {exc.reason}. {details}".strip()) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("LLM request failed: invalid JSON response.") from exc

    text = _extract_text(payload)
    if not text:
        raise RuntimeError("LLM request succeeded but returned an empty reply.")

    return text

