"""Durable call policy. This module intentionally uses only the standard library."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
CLINICS = {"Indiranagar", "Koramangala", "Whitefield"}
SERVICES = {"General consultation", "Braces & aligners", "Teeth whitening", "Dental implants"}
TERMINAL = {"completed", "busy", "no-answer", "failed", "canceled", "stopped"}
ACTIVE = {"creating", "dispatch_unknown", "queued", "initiated", "ringing", "in-progress"}
STAGES = {"identity", "interest", "preference", "confirm", "closed"}


class RuleError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def phone_hash(number: str, secret: str) -> str:
    return hmac.new(secret.encode(), number.encode(), hashlib.sha256).hexdigest()


def valid_phone(number: str) -> bool:
    return bool(re.fullmatch(r"\+[1-9]\d{7,14}", number))


def constant_match(a: str, b: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(a.encode()).digest(), hashlib.sha256(b.encode()).digest())


def clean(value: Any, limit: int = 120) -> str:
    if not isinstance(value, str):
        raise RuleError("A text value is required.", 422)
    result = " ".join(value.split())
    if not result or len(result) > limit or any(ord(c) < 32 for c in value):
        raise RuleError("The text is empty, too long or contains control characters.", 422)
    return result


def callback_time(value: str, now: float) -> str:
    if not isinstance(value, str) or len(value) > 80:
        raise RuleError("Supply an exact ISO date/time with a timezone.", 422)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise RuleError("Supply an exact ISO date/time with a timezone.", 422) from None
    if dt.tzinfo is None:
        raise RuleError("A timezone is required.", 422)
    if not now < dt.timestamp() <= now + 30 * 86400:
        raise RuleError("Choose a future time within 30 days.", 422)
    local = dt.astimezone(IST)
    if not 9 <= local.hour < 20:
        raise RuleError("Callbacks must be between 9 AM and 8 PM India time.", 422)
    return local.isoformat()


def safety_intent(text: str) -> str | None:
    """High-priority English patterns; this is a safety net, not perfect intent recognition."""
    text = " ".join(text.lower().replace("\u2019", "'").strip(" .!?").split())
    if re.search(r"\b(wrong number|you have the wrong person|not the right person|did not request|didn't request)\b", text):
        return "wrong_person"
    if text in {"stop", "hang up", "end this call", "please stop", "no more calls"} or re.search(r"\b(stop calling|stop contacting|do not call|don't call|remove my number|opt out|unsubscribe)\b", text):
        return "stop"
    if re.search(r"\b(can't breathe|cannot breathe|severe bleeding|medical emergency)\b", text):
        return "urgent"
    if re.search(r"\b(speak to a human|talk to a human|real person|human agent|clinic staff)\b", text):
        return "human"
    return None


def affirmative(text: str) -> bool:
    text = " ".join(text.lower().strip(" .!?").split())
    return bool(re.fullmatch(r"(?:yes|yes please|yes i did|yes i requested this call|yes i requested the call|yes i asked for this call|yes that is correct|yes that's correct|that is correct|that's correct|correct|confirmed|please submit|go ahead)", text))


class Store:
    """One-host SQLite store. Cross-process transactions protect dispatch admission."""
    def __init__(self, path: str, secret: str):
        self.path, self.secret = path, secret
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS calls (
              id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, destination TEXT NOT NULL,
              last4 TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
              sid TEXT UNIQUE, sequence INTEGER NOT NULL DEFAULT -1, stage TEXT NOT NULL DEFAULT 'identity',
              outcome TEXT, stopped INTEGER NOT NULL DEFAULT 0, stream_claimed INTEGER NOT NULL DEFAULT 0,
              revision INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL, stop_pending INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tasks (
              call_id TEXT PRIMARY KEY REFERENCES calls(id), reason TEXT NOT NULL,
              priority TEXT NOT NULL DEFAULT 'normal', owner TEXT, resolved INTEGER NOT NULL DEFAULT 0,
              due REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT NOT NULL, kind TEXT NOT NULL,
              detail TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suppressions (destination TEXT PRIMARY KEY, created REAL NOT NULL);
            """)

    @contextmanager
    def db(self, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        if write:
            db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            if write:
                db.execute("COMMIT")
        except BaseException:
            if write:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _event(db, call_id, kind, detail="", now=None):
        db.execute("INSERT INTO events(call_id,kind,detail,created) VALUES(?,?,?,?)", (call_id, kind, detail[:300], now or time.time()))

    @staticmethod
    def _task(db, call_id, reason, priority="normal", now=None):
        now = now or time.time()
        db.execute("""INSERT INTO tasks(call_id,reason,priority,due,updated) VALUES(?,?,?,?,?)
          ON CONFLICT(call_id) DO UPDATE SET reason=excluded.reason, priority=CASE WHEN tasks.priority='urgent' THEN 'urgent' ELSE excluded.priority END,
          resolved=0, updated=excluded.updated""", (call_id, reason, priority, now + 600, now))

    @staticmethod
    def _row(db, call_id):
        row = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
        if row is None:
            raise RuleError("Call not found.", 404)
        return dict(row)

    def get(self, call_id: str) -> dict:
        with self.db() as db:
            row = self._row(db, call_id)
            row["details"] = json.loads(row["details"])
            row["task"] = dict(t) if (t := db.execute("SELECT * FROM tasks WHERE call_id=?", (call_id,)).fetchone()) else None
            row["events"] = [dict(e) for e in db.execute("SELECT kind,detail,created FROM events WHERE call_id=? ORDER BY id DESC LIMIT 50", (call_id,))]
            return row

    def list(self) -> list[dict]:
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM calls ORDER BY created DESC LIMIT 50")]
        return [self.get(i) for i in ids]

    def admit(self, key: str, number: str, context: dict, *, consent: bool, now=None, daily_limit=10, cooldown=180) -> tuple[dict, bool]:
        now = now or time.time()
        try:
            uuid.UUID(key)
        except (ValueError, TypeError, AttributeError):
            raise RuleError("A UUID Idempotency-Key is required.", 422) from None
        if consent is not True or not valid_phone(number):
            raise RuleError("Explicit consent and a configured E.164 test number are required.", 422)
        clinic, service = context.get("clinic"), context.get("service")
        if not isinstance(clinic, str) or not isinstance(service, str) or clinic not in CLINICS or service not in SERVICES:
            raise RuleError("Choose a listed demo clinic and service.", 422)
        if context.get("language", "English") != "English":
            raise RuleError("The live agent is English-only. Other languages need staff.", 422)
        safe = {"clinic": clinic, "service": service, "language": "English"}
        destination = phone_hash(number, self.secret)
        with self.db(True) as db:
            previous = db.execute("SELECT id FROM calls WHERE request_key=?", (key,)).fetchone()
            if previous:
                return {"id": previous[0]}, True
            if db.execute("SELECT 1 FROM suppressions WHERE destination=?", (destination,)).fetchone():
                raise RuleError("Contact is stopped. The owner must record a new test-call consent first.")
            if not 9 <= datetime.fromtimestamp(now, IST).hour < 20:
                raise RuleError("Real calls are allowed from 9 AM to 8 PM India time. The simulation clock does not apply.")
            marks = ",".join("?" for _ in ACTIVE)
            if db.execute(f"SELECT 1 FROM calls WHERE status IN ({marks})", tuple(ACTIVE)).fetchone():
                raise RuleError("A call is active or its dispatch is uncertain. Reconcile it before trying again.")
            day_start = datetime.fromtimestamp(now, IST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            count = db.execute("SELECT COUNT(*) FROM calls WHERE created>=?", (day_start,)).fetchone()[0]
            if count >= daily_limit:
                raise RuleError("The configured daily test-call limit is reached.", 429)
            if db.execute("SELECT 1 FROM calls WHERE created>?", (now - cooldown,)).fetchone():
                raise RuleError("Please wait before placing another test call.", 429)
            call_id = str(uuid.uuid4())
            db.execute("INSERT INTO calls(id,request_key,destination,last4,status,created,updated,details) VALUES(?,?,?,?,?,?,?,?)", (call_id, key, destination, number[-4:], "creating", now, now, json.dumps(safe)))
            self._event(db, call_id, "contact_requested", "Explicit test-call permission recorded", now)
            return {"id": call_id}, False

    def bind(self, call_id: str, sid: str):
        if not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
            raise RuleError("The carrier returned an invalid call reference.", 502)
        with self.db(True) as db:
            r = self._row(db, call_id)
            if r["sid"] and r["sid"] != sid:
                raise RuleError("Call reference mismatch.")
            # A signed status callback may have arrived before the create response.
            status = r["status"] if r["status"] != "creating" else "queued"
            db.execute("UPDATE calls SET sid=?,status=?,updated=? WHERE id=?", (sid, status, time.time(), call_id))
            self._event(db, call_id, "carrier_reference_received")

    def dispatch_failed(self, call_id: str, *, uncertain: bool):
        with self.db(True) as db:
            r = self._row(db, call_id)
            if r["sid"] or r["status"] in TERMINAL:
                return
            db.execute("UPDATE calls SET status=?,updated=? WHERE id=?", ("dispatch_unknown" if uncertain else "failed", time.time(), call_id))
            self._task(db, call_id, "Call dispatch uncertain: check carrier logs; do not redial" if uncertain else "Carrier rejected call; check setup")
            self._event(db, call_id, "dispatch_uncertain" if uncertain else "dispatch_rejected")

    def status(self, call_id: str, sid: str, status: str, sequence: int):
        if status not in {"queued", "initiated", "ringing", "in-progress"} | TERMINAL:
            raise RuleError("Unknown carrier status.", 422)
        with self.db(True) as db:
            r = self._row(db, call_id)
            if r["sid"] and r["sid"] != sid:
                raise RuleError("Carrier call reference mismatch.", 403)
            if sequence <= r["sequence"] or r["status"] in TERMINAL:
                return False
            db.execute("UPDATE calls SET sid=?,status=?,sequence=?,stop_pending=CASE WHEN ? THEN 0 ELSE stop_pending END,updated=? WHERE id=?", (sid, status, sequence, status in TERMINAL, time.time(), call_id))
            self._event(db, call_id, "carrier_status", status)
            if status in TERMINAL and not r["outcome"]:
                self._task(db, call_id, "Call ended without a completed request; staff review required")
            return True

    def claim_stream(self, call_id: str, sid: str):
        with self.db(True) as db:
            r = self._row(db, call_id)
            if r["sid"] != sid or r["stream_claimed"] or r["stopped"] or r["status"] in TERMINAL:
                raise RuleError("This media connection is not authorized.", 403)
            db.execute("UPDATE calls SET stream_claimed=1,status='in-progress',updated=? WHERE id=?", (time.time(), call_id))
            self._event(db, call_id, "media_connected")

    def mutate(self, call_id: str, action: str, values=None, *, now=None):
        values = values or {}
        now = now or time.time()
        with self.db(True) as db:
            r = self._row(db, call_id)
            d = json.loads(r["details"])
            if r["stopped"] or r["stage"] == "closed":
                raise RuleError("This conversation is already closed.")
            if r["status"] in TERMINAL and action in {"identity", "interest", "preference", "submit", "callback"}:
                raise RuleError("The phone call has ended; late model actions cannot change its request.")
            stage, outcome = r["stage"], r["outcome"]
            if action == "identity":
                if stage != "identity" or values.get("confirmed") is not True:
                    raise RuleError("The recipient must confirm this requested test call first.")
                stage = "interest"
            elif action == "interest":
                if stage not in {"interest", "preference", "confirm"}:
                    raise RuleError("Confirm the recipient before collecting interest.")
                if not isinstance(values.get("clinic"), str) or not isinstance(values.get("service"), str) or values["clinic"] not in CLINICS or values["service"] not in SERVICES:
                    raise RuleError("The service or clinic is unsupported.", 422)
                d.update(clinic=values["clinic"], service=values["service"])
                d.pop("appointment_preference", None)
                stage = "preference"
            elif action == "preference":
                if stage not in {"preference", "confirm"}:
                    raise RuleError("Collect clinic and service first.")
                date_time = callback_time(values.get("date_time"), now)
                d["appointment_preference"] = date_time
                stage = "confirm"
            elif action == "submit":
                if stage != "confirm" or values.get("confirmed") is not True or values.get("revision") != r["revision"]:
                    raise RuleError("The current read-back must be explicitly confirmed.")
                outcome, stage = "appointment_requested", "closed"
                self._task(db, call_id, "Confirm appointment request with the clinic; no booking exists", now=now)
            elif action == "callback":
                if stage == "identity":
                    raise RuleError("Confirm the intended recipient before saving a callback preference.")
                if values.get("confirmed") is not True or values.get("revision") != r["revision"]:
                    raise RuleError("The callback preference must be read back and explicitly confirmed.")
                d["callback_preference"] = callback_time(values.get("date_time"), now)
                stage, outcome = "closed", "callback_requested"
                self._task(db, call_id, "Review callback preference; no automatic redial is scheduled", now=now)
            elif action in {"human", "language", "urgent", "technical", "unclear", "voicemail"}:
                stage, outcome = "closed", "staff_followup"
                self._task(db, call_id, {"human":"Patient requested a person", "language":"Unsupported language", "urgent":"Urgent clinical concern; immediate qualified attention required", "technical":"Voice pipeline failed", "unclear":"Could not understand after bounded repair attempts", "voicemail":"Voicemail or automated answer; no sensitive message left"}[action], "urgent" if action == "urgent" else "normal", now)
            elif action in {"stop", "wrong_person"}:
                db.execute("INSERT OR IGNORE INTO suppressions VALUES(?,?)", (r["destination"], now))
                db.execute("UPDATE calls SET stopped=1,stop_pending=1 WHERE id=?", (call_id,))
                outcome, stage = "contact_stopped", "closed"
                # Existing staff tasks must not instruct anyone to call a suppressed contact.
                db.execute("UPDATE tasks SET resolved=1,reason='Contact stopped; no further outreach',updated=? WHERE call_id=?", (now, call_id))
            else:
                raise RuleError("Unsupported conversation action.", 422)
            db.execute("UPDATE calls SET stage=?,outcome=?,details=?,revision=revision+1,updated=? WHERE id=?", (stage, outcome, json.dumps(d), now, call_id))
            self._event(db, call_id, "conversation_" + action, "", now)
        return self.get(call_id)

    def stop_contact(self, call_id: str):
        """Out-of-band stop remains available even after the conversation has closed."""
        with self.db(True) as db:
            r = self._row(db, call_id)
            db.execute("INSERT OR IGNORE INTO suppressions VALUES(?,?)", (r["destination"], time.time()))
            db.execute("UPDATE calls SET stopped=1,stop_pending=1,stage='closed',outcome=COALESCE(outcome,'contact_stopped'),revision=revision+1,updated=? WHERE id=?", (time.time(), call_id))
            db.execute("UPDATE tasks SET resolved=1,reason='Contact stopped; no further outreach',updated=? WHERE call_id=?", (time.time(), call_id))
            self._event(db, call_id, "contact_stopped")

    def stop_result(self, call_id: str, success: bool):
        with self.db(True) as db:
            self._row(db, call_id)
            db.execute("UPDATE calls SET stop_pending=? WHERE id=?", (0 if success else 1, call_id))
            self._event(db, call_id, "carrier_stop_confirmed" if success else "carrier_stop_uncertain")
            if not success:
                note = "Carrier hangup unconfirmed; verify call ended, do not redial"
                task = db.execute("SELECT reason FROM tasks WHERE call_id=?", (call_id,)).fetchone()
                if task and note not in task["reason"]:
                    note = task["reason"] + ". " + note
                elif task:
                    note = task["reason"]
                self._task(db, call_id, note, "urgent")

    def recover(self, now=None, stale_after=300):
        """Never redial jobs left in creating state after a process crash."""
        now = now or time.time()
        with self.db(True) as db:
            for r in db.execute("SELECT id FROM calls WHERE status='creating' AND updated<?", (now - stale_after,)).fetchall():
                db.execute("UPDATE calls SET status='dispatch_unknown',updated=? WHERE id=?", (now, r[0]))
                self._task(db, r[0], "Process restarted during dispatch. Check the carrier before any new call.", "normal", now)

    def resolve_unknown(self, call_id: str, *, carrier_checked: bool):
        if carrier_checked is not True:
            raise RuleError("Explicit carrier-log verification is required.", 422)
        with self.db(True) as db:
            r = self._row(db, call_id)
            if r["status"] != "dispatch_unknown":
                raise RuleError("Only an uncertain dispatch can be cleared this way.")
            db.execute("UPDATE calls SET status='failed',updated=? WHERE id=?", (time.time(), call_id))
            self._event(db, call_id, "operator_reconciled_dispatch", "Operator confirmed no active carrier call")

    def renew_permission(self, number: str, consent: bool):
        if consent is not True:
            raise RuleError("New explicit permission is required.", 422)
        with self.db(True) as db:
            db.execute("DELETE FROM suppressions WHERE destination=?", (phone_hash(number, self.secret),))

    def mark_task(self, call_id: str, action: str):
        with self.db(True) as db:
            self._row(db, call_id)
            task = db.execute("SELECT * FROM tasks WHERE call_id=?", (call_id,)).fetchone()
            if not task:
                raise RuleError("No staff task exists.", 404)
            if task["resolved"]:
                raise RuleError("This staff task is already resolved.")
            if action == "claim":
                if task["owner"]:
                    raise RuleError("This task is already claimed.")
                db.execute("UPDATE tasks SET owner='Clinic operator',updated=? WHERE call_id=?", (time.time(), call_id))
            elif action == "resolve":
                if not task["owner"]:
                    raise RuleError("Claim the task before resolving it.")
                db.execute("UPDATE tasks SET resolved=1,updated=? WHERE call_id=?", (time.time(), call_id))
            else:
                raise RuleError("Unknown staff action.", 422)
            self._event(db, call_id, "staff_" + action)


def media_token(call_id: str, secret: str, expiry: int) -> str:
    body = f"{call_id}.{expiry}"
    return body + "." + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def validate_media_token(token: str, call_id: str, secret: str, now=None) -> bool:
    try:
        request_id, expiry, _ = token.split(".")
        return request_id == call_id and (now or time.time()) <= int(expiry) and constant_match(token, media_token(call_id, secret, int(expiry)))
    except (ValueError, TypeError, AttributeError):
        return False
