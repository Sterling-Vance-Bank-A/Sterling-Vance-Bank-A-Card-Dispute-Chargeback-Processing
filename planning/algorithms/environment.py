from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable


DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "db", "sterling_vance.db")
)
ELICITATION_THRESHOLD = 500.0


@dataclass
class EnvironmentFeedback:
    success: bool
    score: float
    details: str
    source: str


class Environment:
    """Small environment protocol matching the reference toolkit's evaluator seam."""

    def evaluate(self, state: str) -> EnvironmentFeedback:  # pragma: no cover - interface
        raise NotImplementedError


class UngroundedEnvironment(Environment):
    """Ungrounded baseline: model-approved success without external validation."""

    def evaluate(self, state: str) -> EnvironmentFeedback:
        del state
        return EnvironmentFeedback(
            success=True,
            score=1.0,
            details="Candidate self-approved; no external bank validator was consulted.",
            source="ungrounded_model_score",
        )


class GroundedDisputeEnvironment(Environment):
    """Read-only external feedback source backed by Sterling Vance's SQLite DB."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _extract(pattern: str, state: str) -> str | None:
        match = re.search(pattern, state, re.IGNORECASE)
        return match.group(1).upper() if match else None

    def evaluate(self, state: str) -> EnvironmentFeedback:
        dispute_id = self._extract(r"(DISP-\d+)", state)
        analyst_id = self._extract(r"(ANL-\d+)", state)
        lowered = state.lower()

        if not dispute_id:
            return EnvironmentFeedback(False, 0.0, "Missing dispute ID.", "sterling_vance.db")

        with self._connect() as conn:
            dispute = conn.execute(
                "SELECT dispute_id, amount, status FROM disputes WHERE dispute_id = ?",
                (dispute_id,),
            ).fetchone()
            if dispute is None:
                return EnvironmentFeedback(False, 0.0, f"{dispute_id} is not present in the database.", "sterling_vance.db")

            analyst = None
            if analyst_id:
                analyst = conn.execute(
                    "SELECT analyst_id, role FROM analysts WHERE analyst_id = ?",
                    (analyst_id,),
                ).fetchone()

            action = "escalate" if "escalat" in lowered else "refund" if "refund" in lowered else "observe"
            status = str(dispute["status"])
            amount = float(dispute["amount"])

            if action == "refund":
                if status in {"refunded", "denied"}:
                    return EnvironmentFeedback(False, 0.0, f"Refund blocked: dispute already terminal ({status}).", "sterling_vance.db")
                if amount > ELICITATION_THRESHOLD and (analyst is None or analyst["role"] != "senior"):
                    return EnvironmentFeedback(False, 0.0, "Refund blocked: amount above $500 requires a senior analyst.", "sterling_vance.db")
                return EnvironmentFeedback(True, 1.0, "Refund candidate passes current DB constraints.", "sterling_vance.db")

            if action == "escalate":
                if status in {"refunded", "denied", "escalated"}:
                    return EnvironmentFeedback(False, 0.0, f"Escalation blocked: current status is {status}.", "sterling_vance.db")
                if analyst is None or analyst["role"] != "senior":
                    return EnvironmentFeedback(False, 0.0, "Escalation blocked: senior analyst required.", "sterling_vance.db")
                return EnvironmentFeedback(True, 1.0, "Escalation candidate passes current DB constraints.", "sterling_vance.db")

            return EnvironmentFeedback(True, 0.7, "Read-only validation succeeded; no write action requested.", "sterling_vance.db")
