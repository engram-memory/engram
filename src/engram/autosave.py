"""Agent AutoSave — trigger-based automatic memory checkpointing.

Pro feature: Agents never lose their progress. Trigger-based saves on
RAM threshold, message count, timer, session end, or manual.
Incremental saves — only deltas, not everything from scratch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from engram.sessions import SessionManager


@dataclass
class AutoSaveConfig:
    """Configuration for autosave triggers."""

    enabled: bool = True
    interval_seconds: int = 1800  # 30 minutes
    message_threshold: int = 500
    ram_threshold_pct: float = 85.0
    on_session_end: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "message_threshold": self.message_threshold,
            "ram_threshold_pct": self.ram_threshold_pct,
            "on_session_end": self.on_session_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoSaveConfig:
        return cls(
            enabled=data.get("enabled", True),
            interval_seconds=data.get("interval_seconds", 1800),
            message_threshold=data.get("message_threshold", 500),
            ram_threshold_pct=data.get("ram_threshold_pct", 85.0),
            on_session_end=data.get("on_session_end", True),
        )


@dataclass
class Delta:
    """Tracks changes since last checkpoint."""

    stored_ids: list[int] = field(default_factory=list)
    updated_ids: list[int] = field(default_factory=list)
    deleted_ids: list[int] = field(default_factory=list)
    link_ids: list[int] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return (
            len(self.stored_ids)
            + len(self.updated_ids)
            + len(self.deleted_ids)
            + len(self.link_ids)
        )

    @property
    def is_empty(self) -> bool:
        return self.total_changes == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stored_ids": self.stored_ids,
            "updated_ids": self.updated_ids,
            "deleted_ids": self.deleted_ids,
            "link_ids": self.link_ids,
            "total_changes": self.total_changes,
        }

    def reset(self) -> None:
        self.stored_ids.clear()
        self.updated_ids.clear()
        self.deleted_ids.clear()
        self.link_ids.clear()


class AutoSave:
    """Trigger-based automatic memory checkpointing for agents.

    Tracks memory operations (store, update, delete, link) as a delta,
    evaluates configurable triggers, and creates incremental checkpoints.

    Usage::

        from engram.autosave import AutoSave
        from engram.client import Memory

        mem = Memory()
        saver = AutoSave(mem, project="my-agent")
        saver.configure(interval_seconds=600, message_threshold=100)

        # Normal memory operations — delta tracked automatically
        mid = mem.store("some fact", type="fact")
        saver.track_store(mid)

        # After each message exchange
        saver.tick()  # evaluates triggers, saves if needed

        # Manual checkpoint
        saver.checkpoint(reason="end_of_task")

        # Restore after crash
        saver.restore()
    """

    def __init__(
        self,
        session_manager: SessionManager,
        *,
        project: str | None = None,
    ):
        self._session = session_manager
        self._project = project
        self._config = AutoSaveConfig()
        self._delta = Delta()
        self._message_count: int = 0
        self._last_save_at: float = time.monotonic()
        self._total_checkpoints: int = 0
        self._last_trigger: str | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, **kwargs: Any) -> AutoSaveConfig:
        """Update autosave configuration.

        Accepts: enabled, interval_seconds, message_threshold,
        ram_threshold_pct, on_session_end.
        """
        for key, val in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, val)
        return self._config

    @property
    def config(self) -> AutoSaveConfig:
        return self._config

    # ------------------------------------------------------------------
    # Delta tracking
    # ------------------------------------------------------------------

    def track_store(self, memory_id: int | None) -> None:
        """Record that a memory was stored."""
        if memory_id is not None:
            self._delta.stored_ids.append(memory_id)

    def track_update(self, memory_id: int) -> None:
        """Record that a memory was updated."""
        self._delta.updated_ids.append(memory_id)

    def track_delete(self, memory_id: int) -> None:
        """Record that a memory was deleted."""
        self._delta.deleted_ids.append(memory_id)

    def track_link(self, link_id: int | None) -> None:
        """Record that a link was created."""
        if link_id is not None:
            self._delta.link_ids.append(link_id)

    def track_message(self) -> None:
        """Record that a message was exchanged."""
        self._message_count += 1

    @property
    def delta(self) -> Delta:
        return self._delta

    # ------------------------------------------------------------------
    # Trigger evaluation
    # ------------------------------------------------------------------

    def should_save(self, *, ram_pct: float | None = None) -> str | None:
        """Evaluate triggers and return the reason to save, or None.

        Check order (highest priority first):
        1. RAM threshold (emergency)
        2. Message count
        3. Timer interval
        """
        if not self._config.enabled:
            return None

        if self._delta.is_empty and self._message_count == 0:
            return None

        # 1. RAM emergency
        if ram_pct is not None and ram_pct >= self._config.ram_threshold_pct:
            return "ram_threshold"

        # 2. Message count
        if self._message_count >= self._config.message_threshold:
            return "message_threshold"

        # 3. Timer
        elapsed = time.monotonic() - self._last_save_at
        if elapsed >= self._config.interval_seconds:
            return "timer"

        return None

    def tick(self, *, ram_pct: float | None = None) -> dict[str, Any] | None:
        """Evaluate triggers and auto-save if needed.

        Call this after each message exchange or periodically.
        Returns checkpoint info if saved, None otherwise.
        """
        self.track_message()
        reason = self.should_save(ram_pct=ram_pct)
        if reason:
            return self.checkpoint(reason=reason)
        return None

    # ------------------------------------------------------------------
    # Checkpoint & Restore
    # ------------------------------------------------------------------

    def checkpoint(self, reason: str = "manual") -> dict[str, Any]:
        """Save an incremental checkpoint with delta info.

        Returns checkpoint metadata including delta summary.
        """
        delta_summary = self._delta.to_dict()

        # Build summary from delta
        parts = []
        if self._delta.stored_ids:
            parts.append(f"{len(self._delta.stored_ids)} new memories")
        if self._delta.updated_ids:
            parts.append(f"{len(self._delta.updated_ids)} updated")
        if self._delta.deleted_ids:
            parts.append(f"{len(self._delta.deleted_ids)} deleted")
        if self._delta.link_ids:
            parts.append(f"{len(self._delta.link_ids)} new links")

        change_summary = ", ".join(parts) if parts else "no changes"
        summary = f"[autosave:{reason}] {change_summary} (msgs: {self._message_count})"

        # Save checkpoint via session manager
        result = self._session.save_checkpoint(
            project=self._project,
            summary=summary,
            key_facts=[
                f"trigger: {reason}",
                f"delta: {delta_summary}",
                f"messages_since_last_save: {self._message_count}",
            ],
        )

        # Reset counters
        self._delta.reset()
        self._message_count = 0
        self._last_save_at = time.monotonic()
        self._total_checkpoints += 1
        self._last_trigger = reason

        result["reason"] = reason
        result["delta"] = delta_summary
        return result

    def restore(self, checkpoint_id: int | None = None) -> dict[str, Any] | None:
        """Restore from the latest (or specified) checkpoint.

        Returns checkpoint data or None if nothing found.
        """
        if checkpoint_id is not None:
            # Load specific checkpoint by session_id
            return self._session.load_checkpoint(
                session_id=str(checkpoint_id),
            )
        return self._session.load_checkpoint(project=self._project)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return current autosave status."""
        elapsed = time.monotonic() - self._last_save_at
        return {
            "enabled": self._config.enabled,
            "config": self._config.to_dict(),
            "delta": self._delta.to_dict(),
            "message_count": self._message_count,
            "seconds_since_last_save": round(elapsed, 1),
            "total_checkpoints": self._total_checkpoints,
            "last_trigger": self._last_trigger,
            "project": self._project,
        }
