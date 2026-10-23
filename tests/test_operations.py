import json

import pytest

from app import operations


def test_emergency_stop_persists_across_reads(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("ARVEX_STATE_PATH", str(state_file))

    assert operations.emergency_stop_enabled() is False
    assert operations.set_emergency_stop(True) == {"emergency_stop": True}
    assert operations.emergency_stop_enabled() is True
    assert json.loads(state_file.read_text(encoding="utf-8"))["emergency_stop"] is True

    operations.set_emergency_stop(False)
    assert operations.emergency_stop_enabled() is False


def test_invalid_state_fails_safe_and_cannot_be_cleared(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setenv("ARVEX_STATE_PATH", str(state_file))

    assert operations.emergency_stop_enabled() is True
    with pytest.raises(RuntimeError, match="state file is invalid"):
        operations.set_emergency_stop(False)

    # Explicitly setting the stop is allowed and repairs the state file safely.
    operations.set_emergency_stop(True)
    assert operations.emergency_stop_enabled() is True
