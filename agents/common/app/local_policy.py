"""The agent's own, independent authorization. A ticket from the registry is necessary, not sufficient."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DISCLOSURE_RANK = {"score_only": 0, "summary": 1, "evidence": 2}


class LocalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_topics: list[str]
    allowed_entity_classes: list[str] = ["Protein", "Interaction"]
    max_disclosure: str = "summary"
    allowed_protocols: list[str] = ["psi_ca"]
    normalization: str = "fkg-norm/1.0"
    min_eligible_set_size: int = 10
    max_counterpart_set_size: int = 10_000
    pair_daily_limit: int = 10

    @classmethod
    def load(cls, path: Path) -> "LocalPolicy":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def refusal(self, ticket: dict, dev_plaintext_enabled: bool) -> str | None:
        scope = ticket["scope"]
        if scope["protocol"] not in self.allowed_protocols:
            return "local_protocol_not_allowed"
        if scope["protocol"] == "plaintext_dev" and not dev_plaintext_enabled:
            return "local_protocol_not_allowed"
        if scope["normalization"] != self.normalization:
            return "local_normalization_mismatch"
        if not set(scope["topics"]) <= set(self.allowed_topics):
            return "local_topic_not_allowed"
        if not set(scope["entity_classes"]) <= set(self.allowed_entity_classes):
            return "local_entity_class_not_allowed"
        if DISCLOSURE_RANK[scope["disclosure"]] > DISCLOSURE_RANK[self.max_disclosure]:
            return "local_disclosure_not_allowed"
        return None


class AgentState:
    """Single-use ticket roles and per-counterpart comparison counts, persisted on the agent's volume."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._data = {"used": [], "comparisons": []}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data), encoding="utf-8")
        tmp.replace(self._path)

    def claim(self, key: str) -> bool:
        """Mark a (ticket, role, consumer, class) use; False if already used."""
        with self._lock:
            if key in self._data["used"]:
                return False
            self._data["used"].append(key)
            self._save()
            return True

    def count_comparison(self, counterpart: str, ticket_id: str, now: float, limit: int) -> bool:
        """Count a ticket once per counterpart; False if the rolling 24h limit is exhausted."""
        with self._lock:
            window = [c for c in self._data["comparisons"] if c["at"] > now - 24 * 3600]
            if any(c["ticket"] == ticket_id and c["counterpart"] == counterpart for c in window):
                return True
            if sum(1 for c in window if c["counterpart"] == counterpart) >= limit:
                return False
            window.append({"counterpart": counterpart, "ticket": ticket_id, "at": now})
            self._data["comparisons"] = window
            self._save()
            return True
