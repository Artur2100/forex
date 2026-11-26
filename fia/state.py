import json
from pathlib import Path

STATE_PATH = Path("fia_state.json")

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sent": []}

def save_state(state):
    state["sent"] = state.get("sent", [])[-500:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
