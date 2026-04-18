"""JSON shapes for agent and chair replies (parse only; models run in Cursor)."""
from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict, cast


Side = Literal["buy", "sell", "hold"]


class AgentReply(TypedDict, total=False):
    role: str
    side: Side
    entry_price: float | None
    confidence: float
    rationale: str


class ChairReply(TypedDict, total=False):
    side: Side
    entry_price: float | None
    confidence: float
    rationale: str
    dissent_summary: str


def strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", t, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def _extract_json_object(text: str) -> str:
    """Find the first {...} block in text, handling nested braces."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a single JSON object from model output.

    Tries strategies in order:
    1. Strip markdown fence, parse directly.
    2. Extract first {...} block, parse directly.
    3. Run json-repair on the extracted block (handles LLM quirks like
       literal newlines inside strings, trailing commas, truncation, etc.).
    """
    from json_repair import repair_json  # type: ignore[import]

    raw = strip_json_fence(text)

    # Strategy 1: direct parse
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract first {...} block, direct parse
    extracted = _extract_json_object(raw)
    try:
        return cast(dict[str, Any], json.loads(extracted))
    except json.JSONDecodeError:
        pass

    # Strategy 3: repair then parse
    repaired = repair_json(extracted, return_objects=True)
    if isinstance(repaired, dict):
        return cast(dict[str, Any], repaired)
    return cast(dict[str, Any], json.loads(repair_json(extracted)))


def validate_agent_reply(obj: dict[str, Any]) -> AgentReply:
    side = obj.get("side")
    if side not in ("buy", "sell", "hold"):
        raise ValueError(f"Invalid side: {side!r}")
    out: AgentReply = {
        "side": cast(Side, side),
        "confidence": float(obj.get("confidence", 0)),
        "rationale": str(obj.get("rationale", "")),
    }
    if "role" in obj:
        out["role"] = str(obj["role"])
    ep = obj.get("entry_price")
    out["entry_price"] = None if ep is None else float(ep)
    return out


def validate_chair_reply(obj: dict[str, Any]) -> ChairReply:
    side = obj.get("side")
    if side not in ("buy", "sell", "hold"):
        raise ValueError(f"Invalid side: {side!r}")
    out: ChairReply = {
        "side": cast(Side, side),
        "confidence": float(obj.get("confidence", 0)),
        "rationale": str(obj.get("rationale", "")),
    }
    ep = obj.get("entry_price")
    out["entry_price"] = None if ep is None else float(ep)
    if "dissent_summary" in obj:
        out["dissent_summary"] = str(obj["dissent_summary"])
    return out
