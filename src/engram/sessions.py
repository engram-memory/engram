"""Session management — checkpoints, recovery, and conversation indexing.

Pro feature: Allows agents to save/load session state across conversations.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionManager:
    """Manages session checkpoints and context recovery."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(
                os.environ.get(
                    "ENGRAM_DB_PATH",
                    Path.home() / ".engram" / "memory.db",
                )
            )
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    project TEXT,
                    summary TEXT,
                    status TEXT DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    checkpoint_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    checkpoint_num INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    key_facts TEXT,
                    open_tasks TEXT,
                    files_modified TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.commit()

    def _generate_session_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = hashlib.sha256(os.urandom(8)).hexdigest()[:6]
        return f"session_{ts}_{suffix}"

    def _get_or_create_session(self, project: str | None = None) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT session_id FROM sessions
                   WHERE status = 'active' AND (project = ? OR project IS NULL)
                   ORDER BY started_at DESC LIMIT 1""",
                (project,),
            ).fetchone()
            if row:
                return row[0]

        session_id = self._generate_session_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, project, status) VALUES (?, ?, 'active')",
                (session_id, project),
            )
            conn.commit()
        return session_id

    def save_checkpoint(
        self,
        *,
        project: str | None = None,
        summary: str = "",
        key_facts: list[str] | None = None,
        open_tasks: list[str] | None = None,
        files_modified: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save a session checkpoint. Returns checkpoint info."""
        session_id = self._get_or_create_session(project)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(checkpoint_num) FROM checkpoints WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            num = (row[0] or 0) + 1

            conn.execute(
                """INSERT INTO checkpoints
                   (session_id, checkpoint_num, summary, key_facts, open_tasks, files_modified)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    num,
                    summary,
                    json.dumps(key_facts or []),
                    json.dumps(open_tasks or []),
                    json.dumps(files_modified or []),
                ),
            )
            conn.execute(
                "UPDATE sessions SET checkpoint_count = ?, summary = ? WHERE session_id = ?",
                (num, summary, session_id),
            )
            conn.commit()

        return {
            "session_id": session_id,
            "checkpoint_num": num,
            "summary": summary,
            "project": project,
            "created_at": datetime.now().isoformat(),
        }

    def load_checkpoint(
        self,
        *,
        project: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Load the most recent checkpoint."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if session_id:
                row = conn.execute(
                    """SELECT c.*, s.project FROM checkpoints c
                       JOIN sessions s ON c.session_id = s.session_id
                       WHERE c.session_id = ?
                       ORDER BY c.created_at DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
            elif project:
                row = conn.execute(
                    """SELECT c.*, s.project FROM checkpoints c
                       JOIN sessions s ON c.session_id = s.session_id
                       WHERE s.project = ?
                       ORDER BY c.created_at DESC LIMIT 1""",
                    (project,),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT c.*, s.project FROM checkpoints c
                       JOIN sessions s ON c.session_id = s.session_id
                       ORDER BY c.created_at DESC LIMIT 1""",
                ).fetchone()

            if not row:
                return None

            d = dict(row)
            d["key_facts"] = json.loads(d["key_facts"] or "[]")
            d["open_tasks"] = json.loads(d["open_tasks"] or "[]")
            d["files_modified"] = json.loads(d["files_modified"] or "[]")
            return d

    def list_sessions(
        self,
        *,
        project: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List recent sessions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if project:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE project = ? ORDER BY started_at DESC LIMIT ?",
                    (project, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            return [dict(r) for r in rows]

    def recover_context(self, project: str | None = None) -> str:
        """Generate a context recovery summary from the latest checkpoint."""
        cp = self.load_checkpoint(project=project)

        if not cp:
            return "No previous session found. This is a fresh start."

        lines = [
            "## Session Recovery",
            "",
            f"**Last checkpoint:** {cp['created_at']}",
            f"**Project:** {cp.get('project') or 'General'}",
            f"**Checkpoint #{cp['checkpoint_num']}**",
            "",
            "### Summary",
            cp["summary"],
        ]

        if cp["key_facts"]:
            lines.append("\n### Key Facts")
            for fact in cp["key_facts"]:
                lines.append(f"- {fact}")

        if cp["open_tasks"]:
            lines.append("\n### Open Tasks")
            for task in cp["open_tasks"]:
                lines.append(f"- [ ] {task}")

        if cp["files_modified"]:
            lines.append("\n### Files Modified")
            for f in cp["files_modified"]:
                lines.append(f"- {f}")

        return "\n".join(lines)
