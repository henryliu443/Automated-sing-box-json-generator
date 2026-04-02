import json
import os
from datetime import datetime, timezone

STATE_PATH = "/etc/sing-box-deploy/state.json"
_LEGACY_STATE_PATH = "/etc/sing-box/deploy-state.json"
STATE_VERSION = 1


def _migrate_legacy():
    """Move state from the old path (inside sing-box config dir) to the new
    isolated directory, then delete the old file so sing-box -C won't choke."""
    if os.path.isfile(_LEGACY_STATE_PATH):
        if not os.path.isfile(STATE_PATH):
            os.makedirs(os.path.dirname(STATE_PATH), mode=0o700, exist_ok=True)
            with open(_LEGACY_STATE_PATH, "r", encoding="utf-8") as src:
                data = src.read()
            fd = os.open(STATE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as dst:
                dst.write(data)
        os.remove(_LEGACY_STATE_PATH)


def has_state():
    _migrate_legacy()
    return os.path.isfile(STATE_PATH)


def load_state():
    if not has_state():
        return None
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(data):
    _migrate_legacy()
    data["version"] = STATE_VERSION
    data["deployed_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(STATE_PATH), mode=0o700, exist_ok=True)
    fd = os.open(STATE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
