from __future__ import annotations

import json

from services.vps_status import build_vps_status
from services.vps_status_source import load_prepared_vps_payload


def main() -> int:
    payload = load_prepared_vps_payload()
    status = build_vps_status(payload)
    print(json.dumps(status.to_dict(), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
