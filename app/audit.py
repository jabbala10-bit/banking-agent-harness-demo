import json, os, threading
from datetime import datetime, timezone
from .config import AUDIT_PATH
_lock = threading.Lock()
_events = []

def emit(event, session_id=None, transaction_id=None, details=None):
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(), 
        "event": event,
        "session_id": session_id, 
        "transaction_id": transaction_id, 
        "details": details or {}
    }
    with _lock:
        _events.append(row)
        try:
            os.makedirs(os.path.dirname(AUDIT_PATH) or ".", exist_ok=True)
            with open(AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return row

def get_events(limit=100):
    with _lock:
        return list(reversed(_events[-limit:]))

def clear():
    with _lock:
        _events.clear()
        try:
            if os.path.exists(AUDIT_PATH): os.remove(AUDIT_PATH)
        except OSError:
            pass
