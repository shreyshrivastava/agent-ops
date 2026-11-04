"""Small, dependency-free checks for a shareable agent deployment manifest."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REQUIRED_SECTIONS = ("agent", "model", "channels", "controls")
# A key is sensitive when its last word, or last two words, name a secret.
# Matching whole words keeps keys like max_tokens and session_timeout clean.
SECRET_WORDS = {"token", "secret", "password", "passwd", "credential", "credentials", "cookie", "apikey", "session"}
SECRET_PAIRS = {("api", "key"), ("access", "key"), ("private", "key"), ("secret", "key"), ("session", "id")}
SECRET_VALUE_PATTERNS = (
    re.compile(r"^sk-[A-Za-z0-9_-]{8,}"),  # OpenAI / Anthropic style
    re.compile(r"^gh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub
    re.compile(r"^xox[abpr]-"),  # Slack
    re.compile(r"^AKIA[0-9A-Z]{16}$"),  # AWS access key id
    re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\."),  # JWT
    re.compile(r"^Bearer\s+\S+", re.IGNORECASE),
)


def audit_manifest(manifest: Any) -> dict[str, list[str]]:
    """Return validation errors and non-blocking safety warnings for a manifest."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(manifest, Mapping):
        return {"errors": ["Manifest must be a JSON object."], "warnings": warnings}

    for section in REQUIRED_SECTIONS:
        if section not in manifest:
            errors.append(f"Missing required section: {section}.")

    model = manifest.get("model")
    if isinstance(model, Mapping):
        for field in ("provider", "endpoint", "name"):
            if not isinstance(model.get(field), str) or not model[field].strip():
                errors.append(f"model.{field} must be a non-empty string.")

    controls = manifest.get("controls")
    if isinstance(controls, Mapping):
        approvals = controls.get("approval_required_for")
        if not isinstance(approvals, list) or not approvals:
            warnings.append("List high-impact actions in controls.approval_required_for.")
        elif "destructive_operations" not in approvals:
            warnings.append("Require approval for destructive_operations.")

    for path, key, value in _walk(manifest):
        if key is not None and _is_secret_key(key):
            errors.append(f"Potential credential or session field found at {path}; remove it before sharing.")
        if isinstance(value, str) and any(p.search(value.strip()) for p in SECRET_VALUE_PATTERNS):
            errors.append(f"Potential API key value found at {path}; remove it before sharing.")

    return {"errors": errors, "warnings": warnings}


def _is_secret_key(key: str) -> bool:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]
    if not words:
        return False
    return words[-1] in SECRET_WORDS or tuple(words[-2:]) in SECRET_PAIRS


def _walk(value: Any, path: str = "", key: str | None = None):
    """Yield (path, key, value) for every node, containers included, so keys are checked at every depth."""
    yield path, key, value
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            child_path = f"{path}.{child_key}" if path else str(child_key)
            yield from _walk(child, child_path, str(child_key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
