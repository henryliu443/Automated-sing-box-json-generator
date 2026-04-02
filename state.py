import json
import os
from datetime import datetime, timezone

STATE_PATH = "/etc/sing-box/deploy-state.json"
STATE_VERSION = 1


def has_state():
    return os.path.isfile(STATE_PATH)


def load_state():
    if not has_state():
        return None
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(data):
    data["version"] = STATE_VERSION
    data["deployed_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(STATE_PATH), mode=0o700, exist_ok=True)
    # Open with O_CREAT|O_WRONLY|O_TRUNC and mode 0600 so the file is never
    # world-readable, not even briefly between creation and chmod.
    fd = os.open(STATE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
