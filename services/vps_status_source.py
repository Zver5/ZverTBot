from __future__ import annotations

import json
from typing import Any

from config.paths import (
    STATS_JSON,
)


def load_prepared_vps_payload() -> dict[str, Any]:
    try:
        with open(STATS_JSON) as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
