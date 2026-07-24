import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .schemas import AnalyzeEmailRequest, EmailOpenRequest, EmailScanResponse, RiskLevel, ScoreSource, TrackedEmailResponse


class TrackedEmailRepository:
    """SQLite persistence for local development; SQL migration mirrors Supabase PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This vertical slice supports sqlite:/// URLs locally")
        raw_path = database_url.removeprefix("sqlite:///")
        self.database_path = raw_path if raw_path == ":memory:" else str(Path(raw_path).resolve())
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False) if self.database_path == ":memory:" else None
        if self._memory_connection:
            self._memory_connection.row_factory = sqlite3.Row
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._memory_connection or sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            if self._memory_connection is None:
                connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS tracked_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    sender_email TEXT NOT NULL, sender_name TEXT NOT NULL, subject TEXT NOT NULL,
                    first_opened_at TEXT NOT NULL, last_opened_at TEXT NOT NULL, visit_count INTEGER NOT NULL DEFAULT 1,
                    email_risk_score INTEGER NOT NULL, risk_level TEXT NOT NULL, score_source TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(user_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS email_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    interaction_type TEXT NOT NULL CHECK(interaction_type = 'email_open'), event_timestamp TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS email_interactions_lookup_idx
                    ON email_interactions(user_id, message_id, interaction_type, event_timestamp);
                CREATE TABLE IF NOT EXISTS email_scans (
                    scan_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, scanned_at TEXT NOT NULL, result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scan_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    action TEXT NOT NULL, created_at TEXT NOT NULL
                );
                DELETE FROM scan_feedback WHERE id NOT IN (
                    SELECT MIN(id) FROM scan_feedback GROUP BY scan_id, action
                );
                CREATE UNIQUE INDEX IF NOT EXISTS scan_feedback_action_unique_idx
                    ON scan_feedback(scan_id, action);
            """)

    def record_scan(self, result, request: AnalyzeEmailRequest) -> EmailScanResponse:
        suspicious_urls = [item.evidence for item in result.detected_behaviors if item.type == "suspicious_url"]
        technical = [{"type": item.type, "evidence": item.evidence} for item in result.detected_behaviors if item.type in {"sender_domain_mismatch", "suspicious_url"}]
        record = EmailScanResponse(
            **result.model_dump(), subject=request.subject, sender_name=request.sender_name,
            sender_email=request.sender_email, sender_domain=request.sender_domain, url_count=len(request.links),
            suspicious_urls=suspicious_urls, technical_indicators=technical, phishing_probability=None,
            user_reported=False, email_opened=True,
        )
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO email_scans (scan_id, message_id, scanned_at, result_json) VALUES (?, ?, ?, ?)",
                (result.scan_id, result.message_id, result.scanned_at.isoformat(), record.model_dump_json(by_alias=True)),
            )
        return record

    def record_feedback(self, request) -> bool:
        with self.connection() as connection:
            exists = connection.execute("SELECT 1 FROM email_scans WHERE scan_id = ? AND message_id = ?", (request.scan_id, request.message_id)).fetchone()
            if not exists: return False
            connection.execute(
                "INSERT OR IGNORE INTO scan_feedback (scan_id, message_id, action, created_at) VALUES (?, ?, ?, ?)",
                (request.scan_id, request.message_id, request.action, request.created_at.isoformat()),
            )
        return True

    def get_scan(self, scan_id: str) -> EmailScanResponse | None:
        with self.connection() as connection:
            row = connection.execute("SELECT result_json FROM email_scans WHERE scan_id = ?", (scan_id,)).fetchone()
            actions = {item["action"] for item in connection.execute("SELECT action FROM scan_feedback WHERE scan_id = ?", (scan_id,)).fetchall()}
        if not row: return None
        data = json.loads(row["result_json"])
        if "subject" not in data: return None
        data["userReported"] = "reported_suspicious" in actions
        data["viewFullAnalysisSelected"] = "view_full_analysis" in actions
        return EmailScanResponse.model_validate(data)

    def list_scans(self) -> list[EmailScanResponse]:
        with self.connection() as connection:
            rows = connection.execute("SELECT result_json FROM email_scans ORDER BY scanned_at DESC").fetchall()
            reported = {row["scan_id"] for row in connection.execute("SELECT DISTINCT scan_id FROM scan_feedback WHERE action = 'reported_suspicious'").fetchall()}
            viewed = {row["scan_id"] for row in connection.execute("SELECT DISTINCT scan_id FROM scan_feedback WHERE action = 'view_full_analysis'").fetchall()}
        results = []
        for row in rows:
            data = json.loads(row["result_json"])
            if "subject" not in data: continue
            data["userReported"] = data.get("scanId") in reported
            data["viewFullAnalysisSelected"] = data.get("scanId") in viewed
            results.append(EmailScanResponse.model_validate(data))
        return results

    def record_email_open(
        self,
        request: EmailOpenRequest,
        score: int,
        risk_level: RiskLevel,
        deduplication_seconds: int,
    ) -> TrackedEmailResponse:
        opened_at = request.opened_at.astimezone(timezone.utc)
        opened_iso = opened_at.isoformat()
        now_iso = datetime.now(timezone.utc).isoformat()
        cutoff_iso = (opened_at - timedelta(seconds=deduplication_seconds)).isoformat()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                """SELECT 1 FROM email_interactions WHERE user_id = ? AND message_id = ?
                   AND interaction_type = 'email_open' AND event_timestamp BETWEEN ? AND ? LIMIT 1""",
                (request.user_id, request.message_id, cutoff_iso, opened_iso),
            ).fetchone()
            existing = connection.execute(
                "SELECT * FROM tracked_emails WHERE user_id = ? AND message_id = ?",
                (request.user_id, request.message_id),
            ).fetchone()
            if duplicate and existing:
                return self._to_response(existing)

            connection.execute(
                """INSERT INTO email_interactions
                   (user_id, message_id, interaction_type, event_timestamp, metadata, created_at)
                   VALUES (?, ?, 'email_open', ?, ?, ?)""",
                (request.user_id, request.message_id, opened_iso, json.dumps({"source": "extension-mock-adapter"}), now_iso),
            )
            if existing:
                connection.execute(
                    """UPDATE tracked_emails SET sender_email = ?, sender_name = ?, subject = ?,
                       last_opened_at = ?, visit_count = visit_count + 1, email_risk_score = ?, risk_level = ?,
                       score_source = ?, updated_at = ? WHERE user_id = ? AND message_id = ?""",
                    (str(request.sender_email), request.sender_name, request.subject, opened_iso, score, risk_level.value,
                     ScoreSource.MOCK_RULE_BASED.value, now_iso, request.user_id, request.message_id),
                )
            else:
                connection.execute(
                    """INSERT INTO tracked_emails
                       (user_id, message_id, sender_email, sender_name, subject, first_opened_at, last_opened_at,
                        visit_count, email_risk_score, risk_level, score_source, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
                    (request.user_id, request.message_id, str(request.sender_email), request.sender_name, request.subject,
                     opened_iso, opened_iso, score, risk_level.value, ScoreSource.MOCK_RULE_BASED.value, now_iso, now_iso),
                )
            row = connection.execute(
                "SELECT * FROM tracked_emails WHERE user_id = ? AND message_id = ?",
                (request.user_id, request.message_id),
            ).fetchone()
            return self._to_response(row)

    def list_tracked_emails(self) -> list[TrackedEmailResponse]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM tracked_emails ORDER BY last_opened_at DESC").fetchall()
        return [self._to_response(row) for row in rows]

    def get_tracked_email(self, message_id: str) -> TrackedEmailResponse | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM tracked_emails WHERE message_id = ? ORDER BY updated_at DESC LIMIT 1", (message_id,)
            ).fetchone()
        return self._to_response(row) if row else None

    @staticmethod
    def _to_response(row: sqlite3.Row) -> TrackedEmailResponse:
        return TrackedEmailResponse(
            message_id=row["message_id"], sender_email=row["sender_email"], sender_name=row["sender_name"],
            subject=row["subject"], visit_count=row["visit_count"], email_risk_score=row["email_risk_score"],
            risk_level=row["risk_level"], score_source=row["score_source"],
            first_opened_at=row["first_opened_at"], last_opened_at=row["last_opened_at"],
        )
