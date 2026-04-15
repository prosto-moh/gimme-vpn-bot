from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def awg_creation_date() -> str:
    return datetime.now().strftime("%a %b %d %H:%M:%S %Y")
