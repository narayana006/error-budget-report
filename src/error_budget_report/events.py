"""Read good/total event counts from CSV.

Expected columns (header row required, order free, extra columns ignored):

    timestamp  start of the bucket: ISO 8601 or a plain date; no zone means UTC
    slo        SLO name, matching metadata.name in the definitions
    good       events that met the objective in this bucket
    total      all valid events in this bucket
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import IO

REQUIRED_COLUMNS = ("timestamp", "slo", "good", "total")


class EventFileError(ValueError):
    """The events file is missing columns or contains a row that cannot be parsed."""


@dataclass(frozen=True)
class Bucket:
    time: datetime  # timezone-aware, UTC
    good: float
    total: float

    @property
    def bad(self) -> float:
        return self.total - self.good


def parse_timestamp(text: str) -> datetime:
    text = text.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _count(raw: str, name: str, line_no: int) -> float:
    try:
        value = float(raw.strip())
    except ValueError:
        raise EventFileError(f"line {line_no}: {name} {raw!r} is not a number") from None
    if not (0 <= value < float("inf")):
        raise EventFileError(f"line {line_no}: {name} must be a non-negative finite number")
    return value


def read_events(handle: IO[str]) -> dict[str, list[Bucket]]:
    """Return ``{slo name: buckets sorted by time}``. Rows sharing a timestamp are summed."""
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise EventFileError("events file is empty (no header row)")
    header = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise EventFileError("events file is missing required column(s): " + ", ".join(missing))

    sums: dict[str, dict[datetime, list[float]]] = defaultdict(dict)
    for line_no, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue
        stamp = raw[header["timestamp"]] or ""
        try:
            when = parse_timestamp(stamp)
        except ValueError:
            raise EventFileError(f"line {line_no}: timestamp {stamp!r} is not ISO 8601") from None
        name = (raw[header["slo"]] or "").strip()
        if not name:
            raise EventFileError(f"line {line_no}: slo is empty")
        good = _count(raw[header["good"]] or "", "good", line_no)
        total = _count(raw[header["total"]] or "", "total", line_no)
        if good > total:
            raise EventFileError(f"line {line_no}: good ({good:g}) is larger than total ({total:g})")
        slot = sums[name].setdefault(when, [0.0, 0.0])
        slot[0] += good
        slot[1] += total

    return {
        name: [Bucket(when, good, total) for when, (good, total) in sorted(by_time.items())]
        for name, by_time in sums.items()
    }


def read_events_file(path: str) -> dict[str, list[Bucket]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return read_events(handle)
