"""Provider-level LLM call functions (OpenAI, Google Gemini, Anthropic).

Priority for Anthropic models (RiskAgent / Chair):
  1. CLAUDE_PROXY_URL set   → call via local Claude Code proxy (claude-max-api-proxy)
                              Uses your Claude Pro/Max subscription, no API key needed.
                              Start proxy: npm install -g claude-max-api-proxy && claude-max-api
  2. ANTHROPIC_API_KEY set  → call Anthropic API directly
  3. Neither set            → fall back to GPT-4o so the debate still runs
"""
from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# Model name constants
# ---------------------------------------------------------------------------
OPENAI_MODEL  = "gpt-4o"
GEMINI_MODEL  = "gemini-2.5-flash"
SONNET_MODEL  = "claude-3-5-sonnet-20241022"
OPUS_MODEL    = "claude-3-opus-20240229"

# Model names as exposed by claude-max-api-proxy / OCP
PROXY_SONNET_MODEL = os.environ.get("PROXY_SONNET_MODEL", "claude-sonnet-4-6")
PROXY_OPUS_MODEL   = os.environ.get("PROXY_OPUS_MODEL",   "claude-opus-4-6")


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def call_openai(system: str, user: str, *, model: str = OPENAI_MODEL) -> str:
    """Call OpenAI chat completions API."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

def call_gemini(system: str, user: str, *, model: str = GEMINI_MODEL) -> str:
    """Call Google Gemini API via the google-genai SDK."""
    from google import genai          # type: ignore[import]
    from google.genai import types    # type: ignore[import]

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY is not set in .env")

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=(
                system
                + "\n\nCRITICAL: reply with a single raw JSON object only."
                " No markdown, no explanation, no text before or after the JSON."
            ),
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )
    return resp.text.strip()


# ---------------------------------------------------------------------------
# Anthropic — proxy, direct API key, or GPT-4o fallback
# ---------------------------------------------------------------------------

def _claude_proxy_url() -> str:
    return os.environ.get("CLAUDE_PROXY_URL", "").strip()


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _call_via_claude_proxy(system: str, user: str, *, model: str) -> str:
    """Call Claude through the local claude-max-api-proxy (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(base_url=_claude_proxy_url(), api_key="not-needed")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


def _call_anthropic_direct(system: str, user: str, *, model: str) -> str:
    """Call Anthropic Messages API directly using ANTHROPIC_API_KEY."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.3,
    )
    return resp.content[0].text.strip()


def call_anthropic(system: str, user: str, *, model: str = SONNET_MODEL) -> str:
    """Call Claude Sonnet. Priority: Claude proxy → API key → GPT-4o fallback."""
    if _claude_proxy_url():
        return _call_via_claude_proxy(system, user, model=PROXY_SONNET_MODEL)
    if _has_anthropic_key():
        return _call_anthropic_direct(system, user, model=model)
    return call_openai(system, user, model=OPENAI_MODEL)


def call_opus(system: str, user: str) -> str:
    """Call Claude Opus. Priority: Claude proxy → API key → GPT-4o fallback."""
    if _claude_proxy_url():
        return _call_via_claude_proxy(system, user, model=PROXY_OPUS_MODEL)
    if _has_anthropic_key():
        return _call_anthropic_direct(system, user, model=OPUS_MODEL)
    return call_openai(system, user, model=OPENAI_MODEL)


# ---------------------------------------------------------------------------
# Introspection helper used by the UI
# ---------------------------------------------------------------------------

def anthropic_mode() -> str:
    if _claude_proxy_url():
        return f"Claude subscription proxy  ({_claude_proxy_url()})"
    if _has_anthropic_key():
        return "Anthropic API key"
    return "GPT-4o fallback  (no ANTHROPIC_API_KEY or CLAUDE_PROXY_URL)"
