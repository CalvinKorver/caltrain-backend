from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings


Severity = Literal["NO_ALERT", "INFO", "WARNING", "CRITICAL"]


@dataclass(frozen=True)
class ClassificationResult:
    severity: Severity
    title: str
    message: str
    evidence_sources: list[str]
    raw_output: dict


def _load_system_prompt() -> str:
    # Local file-based prompt keeps editing simple.
    # This is safe for MVP; for production you might use DB/versioned prompts.
    try:
        import pathlib

        p = pathlib.Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.md"
        return p.read_text(encoding="utf-8")
    except Exception:
        return "Classify transit delay severity and return strict JSON."


def _severity_examples_for_model() -> list[str]:
    try:
        import pathlib

        p = pathlib.Path(__file__).resolve().parents[2] / "prompts" / "severity_examples.jsonl"
        lines = p.read_text(encoding="utf-8").splitlines()
        return [ln for ln in lines if ln.strip()]
    except Exception:
        return []


def _parse_json_from_model(content: str) -> dict:
    content = (content or "").strip()
    try:
        return json.loads(content)
    except Exception:
        # Best-effort recovery: extract the first {...} JSON object.
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"severity": "NO_ALERT"}
        snippet = content[start : end + 1]
        return json.loads(snippet)


@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(4))
def classify_severity(report_text: str, source_evidence: list[str]) -> ClassificationResult:
    """
    Claude call to classify incident severity.

    Expected structured JSON output:
      {
        "severity": "NO_ALERT" | "INFO" | "WARNING" | "CRITICAL",
        "title": "...",
        "message": "...",
        "evidence_sources": ["511","reddit",...]
      }
    """
    s = get_settings()
    if not s.anthropic_api_key:
        # Fail safely if key isn't configured.
        return ClassificationResult(
            severity="NO_ALERT",
            title="No alert",
            message="Anthropic not configured.",
            evidence_sources=source_evidence,
            raw_output={"error": "missing_anthropic_api_key"},
        )

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    system_prompt = _load_system_prompt()
    examples = _severity_examples_for_model()

    # Few-shot in a lightweight way: embed example JSONL as context.
    examples_block = "\n".join(examples) if examples else ""

    user_prompt = {
        "report_text": report_text,
        "evidence_sources": source_evidence,
        "instructions": (
            "Return ONLY valid JSON matching the schema. Do not wrap in markdown. "
            "Be conservative: choose NO_ALERT unless delays/instructions are clearly supported."
        ),
        "schema": {
            "severity": ["NO_ALERT", "INFO", "WARNING", "CRITICAL"],
            "title": "short title",
            "message": "SMS-ready summary, <= 280 chars preferred",
            "evidence_sources": ["511", "reddit"],
        },
    }

    resp = client.messages.create(
        model=s.anthropic_model,
        max_tokens=300,
        temperature=0.2,
        system=system_prompt + ("\n\nFew-shot examples (JSONL):\n" + examples_block if examples_block else ""),
        messages=[{"role": "user", "content": json.dumps(user_prompt)}],
    )

    content = resp.content[0].text if resp.content else ""
    parsed = _parse_json_from_model(content)

    severity = parsed.get("severity", "NO_ALERT")
    if severity not in {"NO_ALERT", "INFO", "WARNING", "CRITICAL"}:
        severity = "NO_ALERT"

    return ClassificationResult(
        severity=severity,
        title=str(parsed.get("title", "Caltrain alert")),
        message=str(parsed.get("message", ""))[:280],
        evidence_sources=list(parsed.get("evidence_sources", source_evidence)),
        raw_output=parsed,
    )

