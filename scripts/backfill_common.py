from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class DateWindow:
    start_date: str
    end_date: str


def parse_iso_date(raw_value: str) -> date:
    return date.fromisoformat(raw_value)


def iter_monthly_windows(start_date: str, end_date: str) -> Iterator[DateWindow]:
    current = parse_iso_date(start_date)
    final = parse_iso_date(end_date)
    if current > final:
        raise ValueError("start_date must be on or before end_date")

    while current <= final:
        next_month_anchor = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        window_end = min(next_month_anchor - timedelta(days=1), final)
        yield DateWindow(
            start_date=current.isoformat(),
            end_date=window_end.isoformat(),
        )
        current = window_end + timedelta(days=1)


def write_payload_to_local_path(root_dir: str | Path, object_key: str, payload: dict) -> Path:
    output_path = Path(root_dir) / object_key
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
