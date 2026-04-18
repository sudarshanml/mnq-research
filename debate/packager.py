"""Write debate Markdown artifacts for use in Cursor Chat / Composer."""
from __future__ import annotations

from pathlib import Path

from . import prompts


def write_debate_artifacts(out_dir: str | Path, snapshot_md: str) -> Path:
    """
    Write snapshot + instruction files. User runs debate in Cursor (model picker in UI).
    """
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "snapshot.md").write_text(snapshot_md, encoding="utf-8")

    instructions = "\n".join(
        [
            "# MNQ multi-agent debate (Cursor)",
            "",
            prompts.DISCLAIMER,
            "",
            "## How to run in Cursor",
            "",
            "1. Open `snapshot.md` in this folder (or keep it visible).",
            "2. For **each** role below: start a **new Chat** (or Composer), **pick a model in the Cursor UI**,",
            "   paste the role block + the full contents of `snapshot.md`, and copy the model JSON reply into a file:",
            "   `replies/trend.json`, `replies/meanrev.json`, `replies/risk.json` (create `replies/` if needed).",
            "3. Open `chair_prompt.md`, paste the three JSON files' contents where indicated, pick a **chair** model,",
            "   save the final JSON as `replies/chair_final.json`.",
            "",
            "**Shortcut:** use one Chat and ask a single model to output all three agent JSONs plus chair in one response;",
            "splitting roles is only needed if you want different models per role.",
            "",
            "---",
            "",
            "## Role: TrendAgent",
            "",
            prompts.ROLE_TREND,
            "",
            prompts.JSON_AGENT_CONTRACT,
            "",
            "---",
            "",
            "## Role: MeanRevertAgent",
            "",
            prompts.ROLE_MEANREV,
            "",
            prompts.JSON_AGENT_CONTRACT,
            "",
            "---",
            "",
            "## Role: RiskAgent",
            "",
            prompts.ROLE_RISK,
            "",
            prompts.JSON_AGENT_CONTRACT,
            "",
        ]
    )
    (root / "debate_instructions.md").write_text(instructions, encoding="utf-8")

    chair = "\n".join(
        [
            "# Chair — final decision",
            "",
            prompts.DISCLAIMER,
            "",
            prompts.CHAIR_SYSTEM,
            "",
            "## Market snapshot",
            "",
            "(Paste full contents of `snapshot.md` here, or @-reference the file in Cursor.)",
            "",
            "## Agent JSON replies",
            "",
            "Paste **TrendAgent** JSON:",
            "",
            "```json",
            "<paste replies/trend.json>",
            "```",
            "",
            "Paste **MeanRevertAgent** JSON:",
            "",
            "```json",
            "<paste replies/meanrev.json>",
            "```",
            "",
            "Paste **RiskAgent** JSON:",
            "",
            "```json",
            "<paste replies/risk.json>",
            "```",
            "",
            "## Output",
            "",
            prompts.JSON_CHAIR_CONTRACT,
            "",
        ]
    )
    (root / "chair_prompt.md").write_text(chair, encoding="utf-8")

    replies = root / "replies"
    replies.mkdir(exist_ok=True)
    (replies / "README.txt").write_text(
        "Place model JSON outputs here:\n"
        "  trend.json, meanrev.json, risk.json, chair_final.json\n",
        encoding="utf-8",
    )

    return root
