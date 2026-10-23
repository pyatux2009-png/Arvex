"""Persistent operational safety controls for Arvex.

The emergency stop blocks all new executions; it does not attempt to cancel
exchange orders or close an existing position automatically.
"""
import json
import os
import tempfile
import threading
from pathlib import Path

_LOCK = threading.RLock()


def _state_path() -> Path:
    configured = os.getenv("ARVEX_STATE_PATH", "arvex_state.json").strip()
    return Path(configured or "arvex_state.json")


def _read_state() -> dict:
    path = _state_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        # Fail safe: malformed state must never silently clear an emergency stop.
        return {"emergency_stop": True, "state_error": "State file unreadable or invalid"}


def _write_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def emergency_stop_enabled() -> bool:
    with _LOCK:
        state = _read_state()
        return bool(state.get("emergency_stop", False) or state.get("state_error"))


def set_emergency_stop(enabled: bool) -> dict:
    with _LOCK:
        state = _read_state()
        # Refuse to clear a corrupt state file automatically. An operator must
        # inspect/fix it rather than accidentally re-enable execution.
        if state.get("state_error") and not enabled:
            raise RuntimeError("Safety state file is invalid; inspect it before clearing emergency stop.")
        state["emergency_stop"] = bool(enabled)
        state.pop("state_error", None)
        _write_state(state)
        return {"emergency_stop": bool(enabled)}
