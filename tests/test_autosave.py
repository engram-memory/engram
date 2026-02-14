"""Tests for Agent AutoSave (Phase 4)."""

from pathlib import Path

import pytest

from engram.autosave import AutoSave, AutoSaveConfig, Delta
from engram.client import Memory
from engram.config import EngramConfig
from engram.sessions import SessionManager

# ------------------------------------------------------------------
# Delta tracking tests
# ------------------------------------------------------------------


class TestDelta:
    def test_empty_delta(self):
        d = Delta()
        assert d.is_empty is True
        assert d.total_changes == 0

    def test_track_changes(self):
        d = Delta()
        d.stored_ids.append(1)
        d.stored_ids.append(2)
        d.updated_ids.append(3)
        d.deleted_ids.append(4)
        d.link_ids.append(5)
        assert d.total_changes == 5
        assert d.is_empty is False

    def test_reset(self):
        d = Delta()
        d.stored_ids.extend([1, 2, 3])
        d.updated_ids.append(4)
        d.reset()
        assert d.is_empty is True
        assert d.total_changes == 0

    def test_to_dict(self):
        d = Delta()
        d.stored_ids.append(1)
        data = d.to_dict()
        assert data["stored_ids"] == [1]
        assert data["total_changes"] == 1


# ------------------------------------------------------------------
# AutoSaveConfig tests
# ------------------------------------------------------------------


class TestAutoSaveConfig:
    def test_defaults(self):
        cfg = AutoSaveConfig()
        assert cfg.enabled is True
        assert cfg.interval_seconds == 1800
        assert cfg.message_threshold == 500
        assert cfg.ram_threshold_pct == 85.0
        assert cfg.on_session_end is True

    def test_to_dict_from_dict(self):
        cfg = AutoSaveConfig(interval_seconds=600, message_threshold=100)
        data = cfg.to_dict()
        cfg2 = AutoSaveConfig.from_dict(data)
        assert cfg2.interval_seconds == 600
        assert cfg2.message_threshold == 100


# ------------------------------------------------------------------
# AutoSave engine tests
# ------------------------------------------------------------------


@pytest.fixture()
def saver(tmp_path: Path) -> AutoSave:
    sess = SessionManager(db_path=tmp_path / "autosave_test.db")
    return AutoSave(sess, project="test-project")


class TestAutoSaveEngine:
    def test_configure(self, saver: AutoSave):
        cfg = saver.configure(interval_seconds=120, message_threshold=50)
        assert cfg.interval_seconds == 120
        assert cfg.message_threshold == 50

    def test_track_store(self, saver: AutoSave):
        saver.track_store(1)
        saver.track_store(2)
        assert saver.delta.stored_ids == [1, 2]
        assert saver.delta.total_changes == 2

    def test_track_update(self, saver: AutoSave):
        saver.track_update(5)
        assert saver.delta.updated_ids == [5]

    def test_track_delete(self, saver: AutoSave):
        saver.track_delete(3)
        assert saver.delta.deleted_ids == [3]

    def test_track_link(self, saver: AutoSave):
        saver.track_link(10)
        saver.track_link(None)  # should be ignored
        assert saver.delta.link_ids == [10]

    def test_track_store_none_ignored(self, saver: AutoSave):
        saver.track_store(None)
        assert saver.delta.is_empty

    def test_should_save_disabled(self, saver: AutoSave):
        saver.configure(enabled=False)
        saver.track_store(1)
        saver.track_message()
        assert saver.should_save() is None

    def test_should_save_empty_delta(self, saver: AutoSave):
        # No changes, no messages — should not save
        assert saver.should_save() is None

    def test_should_save_ram_threshold(self, saver: AutoSave):
        saver.configure(ram_threshold_pct=80.0)
        saver.track_store(1)
        assert saver.should_save(ram_pct=90.0) == "ram_threshold"
        assert saver.should_save(ram_pct=70.0) is None

    def test_should_save_message_threshold(self, saver: AutoSave):
        saver.configure(message_threshold=3)
        saver.track_store(1)
        saver.track_message()
        saver.track_message()
        assert saver.should_save() is None
        saver.track_message()
        assert saver.should_save() == "message_threshold"

    def test_should_save_timer(self, saver: AutoSave):
        saver.configure(interval_seconds=0)  # immediate
        saver.track_store(1)
        assert saver.should_save() == "timer"

    def test_checkpoint_saves_and_resets(self, saver: AutoSave):
        saver.track_store(1)
        saver.track_store(2)
        saver.track_update(3)
        saver.track_message()
        saver.track_message()

        result = saver.checkpoint(reason="test")
        assert result["reason"] == "test"
        assert result["delta"]["total_changes"] == 3
        assert "2 new memories" in result["summary"]
        assert "1 updated" in result["summary"]

        # Delta should be reset
        assert saver.delta.is_empty
        assert saver._message_count == 0
        assert saver._total_checkpoints == 1

    def test_checkpoint_empty_delta(self, saver: AutoSave):
        result = saver.checkpoint(reason="manual")
        assert result["reason"] == "manual"
        assert "no changes" in result["summary"]

    def test_tick_auto_saves(self, saver: AutoSave):
        saver.configure(message_threshold=2)
        saver.track_store(1)

        # First tick — message count = 1, below threshold
        result = saver.tick()
        assert result is None

        # Second tick — message count = 2, triggers save
        result = saver.tick()
        assert result is not None
        assert result["reason"] == "message_threshold"

    def test_tick_with_ram(self, saver: AutoSave):
        saver.configure(ram_threshold_pct=80.0)
        saver.track_store(1)
        result = saver.tick(ram_pct=95.0)
        assert result is not None
        assert result["reason"] == "ram_threshold"

    def test_restore(self, saver: AutoSave):
        saver.track_store(1)
        saver.checkpoint(reason="test")

        loaded = saver.restore()
        assert loaded is not None
        assert "test" in loaded.get("summary", "")

    def test_restore_empty(self, tmp_path: Path):
        sess = SessionManager(db_path=tmp_path / "empty_restore.db")
        sv = AutoSave(sess, project="nonexistent")
        assert sv.restore() is None

    def test_status(self, saver: AutoSave):
        saver.track_store(1)
        saver.track_message()
        status = saver.status()
        assert status["enabled"] is True
        assert status["message_count"] == 1
        assert status["delta"]["total_changes"] == 1
        assert status["total_checkpoints"] == 0
        assert status["project"] == "test-project"

    def test_trigger_priority_ram_first(self, saver: AutoSave):
        """RAM trigger should take priority over message count."""
        saver.configure(
            message_threshold=1,
            ram_threshold_pct=80.0,
            interval_seconds=0,
        )
        saver.track_store(1)
        saver.track_message()
        # All three triggers active — RAM should win
        assert saver.should_save(ram_pct=90.0) == "ram_threshold"

    def test_multiple_checkpoints_increment(self, saver: AutoSave):
        saver.track_store(1)
        saver.checkpoint(reason="first")
        assert saver._total_checkpoints == 1

        saver.track_store(2)
        saver.checkpoint(reason="second")
        assert saver._total_checkpoints == 2
        assert saver._last_trigger == "second"


# ------------------------------------------------------------------
# Memory client integration tests
# ------------------------------------------------------------------


@pytest.fixture()
def mem(tmp_path: Path) -> Memory:
    config = EngramConfig(db_path=tmp_path / "client_autosave.db")
    return Memory(config=config)


class TestMemoryAutoSave:
    def test_autosave_returns_controller(self, mem: Memory):
        saver = mem.autosave(project="test")
        assert isinstance(saver, AutoSave)
        assert saver.config.enabled is True

    def test_autosave_custom_config(self, mem: Memory):
        saver = mem.autosave(
            project="test",
            interval_minutes=10,
            message_threshold=100,
            ram_threshold_pct=90.0,
        )
        assert saver.config.interval_seconds == 600
        assert saver.config.message_threshold == 100
        assert saver.config.ram_threshold_pct == 90.0

    def test_checkpoint_method(self, mem: Memory):
        mem.store("test fact")
        result = mem.checkpoint(reason="test", project="test-proj")
        assert "checkpoint_num" in result or "reason" in result

    def test_restore_method(self, mem: Memory):
        mem.checkpoint(reason="test", project="restore-test")
        loaded = mem.restore(project="restore-test")
        assert loaded is not None

    def test_checkpoints_method(self, mem: Memory):
        mem.checkpoint(reason="list-test", project="list-proj")
        sessions = mem.checkpoints(project="list-proj")
        assert len(sessions) >= 1

    def test_full_autosave_flow(self, mem: Memory):
        """End-to-end: store memories, auto-save on threshold, restore."""
        saver = mem.autosave(project="e2e-test", message_threshold=3)

        # Store some memories and track them
        for i in range(3):
            mid = mem.store(f"fact {i}", importance=5 + i)
            saver.track_store(mid)

        # Tick messages — should trigger on 3rd
        result1 = saver.tick()
        assert result1 is None
        result2 = saver.tick()
        assert result2 is None
        result3 = saver.tick()
        assert result3 is not None
        assert result3["reason"] == "message_threshold"
        assert result3["delta"]["total_changes"] == 3

        # Delta should be clean now
        assert saver.delta.is_empty
        assert saver._message_count == 0

        # Restore
        loaded = saver.restore()
        assert loaded is not None
