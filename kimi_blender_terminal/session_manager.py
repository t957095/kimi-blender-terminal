"""
SessionManager — persists Blender-side conversation sessions independently of Kimi CLI sessions.

Storage: ~/.kimi/blender-terminal/sessions.json
Each session stores:
  - name, uuid
  - kimi_session_id (the CLI -r session)
  - history (last 50 messages for preview)
  - created_at, updated_at
  - optional blender_file path
"""

import json
import os
import time
import uuid

SESSION_DIR = os.path.expanduser(r"~\.kimi\blender-terminal")
SESSION_FILE = os.path.join(SESSION_DIR, "sessions.json")


def _ensure_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)


def _load_data() -> dict:
    _ensure_dir()
    if os.path.isfile(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sessions": {}, "active_session": None}


def _save_data(data: dict):
    _ensure_dir()
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class SessionManager:
    def __init__(self):
        self._data = _load_data()

    def list_sessions(self) -> list:
        """Return list of session dicts sorted by updated_at desc."""
        sessions = self._data.get("sessions", {})
        result = []
        for sid, s in sessions.items():
            entry = dict(s)
            entry["uuid"] = sid
            result.append(entry)
        result.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return result

    def get_active(self) -> dict:
        aid = self._data.get("active_session")
        if aid and aid in self._data.get("sessions", {}):
            s = dict(self._data["sessions"][aid])
            s["uuid"] = aid
            return s
        return None

    def create(self, name: str = None, kimi_session_id: str = None) -> str:
        sid = str(uuid.uuid4())
        now = time.time()
        self._data["sessions"][sid] = {
            "name": name or f"Session {len(self._data['sessions']) + 1}",
            "kimi_session_id": kimi_session_id or "",
            "created_at": now,
            "updated_at": now,
            "history": [],
            "blender_file": "",
        }
        self._data["active_session"] = sid
        _save_data(self._data)
        return sid

    def save(self, sid: str, history: list = None, kimi_session_id: str = None, blender_file: str = None):
        if sid not in self._data.get("sessions", {}):
            return False
        s = self._data["sessions"][sid]
        if history is not None:
            s["history"] = [{"role": h.get("role"), "content": h.get("content")} for h in history[-50:]]
        if kimi_session_id is not None:
            s["kimi_session_id"] = kimi_session_id
        if blender_file is not None:
            s["blender_file"] = blender_file
        s["updated_at"] = time.time()
        _save_data(self._data)
        return True

    def load(self, sid: str) -> dict:
        if sid not in self._data.get("sessions", {}):
            return None
        self._data["active_session"] = sid
        _save_data(self._data)
        s = dict(self._data["sessions"][sid])
        s["uuid"] = sid
        return s

    def delete(self, sid: str) -> bool:
        if sid not in self._data.get("sessions", {}):
            return False
        del self._data["sessions"][sid]
        if self._data.get("active_session") == sid:
            self._data["active_session"] = None
        _save_data(self._data)
        return True

    def rename(self, sid: str, name: str) -> bool:
        if sid not in self._data.get("sessions", {}):
            return False
        self._data["sessions"][sid]["name"] = name
        self._data["sessions"][sid]["updated_at"] = time.time()
        _save_data(self._data)
        return True

    def set_active(self, sid: str):
        if sid in self._data.get("sessions", {}):
            self._data["active_session"] = sid
            _save_data(self._data)

    def active_id(self) -> str:
        return self._data.get("active_session")
