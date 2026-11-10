"""Regenerate examples/events.csv.

Synthetic data: 28 days of hourly good/total counts for the four example SLOs.

* checkout-availability   a bad deploy on 2025-06-26 (3 hours of elevated 5xx)
                          plus a smaller blip on 2025-06-11 spends the whole budget
* checkout-latency        steadily slow since 2025-06-24; budget burning but not gone
* search-availability     healthy throughout
* notifications-delivery  healthy, 14-day window

Run from the repository root:  python examples/generate_sample.py
"""

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2025, 6, 2, tzinfo=timezone.utc)
HOURS = 28 * 24

# slo -> (peak requests per hour, normal failure ratio)
SLOS = {
    "checkout-availability": (42000, 0.0004),
    "checkout-latency": (42000, 0.004),
    "search-availability": (118000, 0.0012),
    "notifications-delivery": (9000, 0.003),
}


def failure_ratio(slo: str, when: datetime, normal: float) -> float:
    if slo == "checkout-availability":
        if when.date() == datetime(2025, 6, 26).date() and 14 <= when.hour < 17:
            return 0.085
        if when.date() == datetime(2025, 6, 11).date() and when.hour == 9:
            return 0.03
    if slo == "checkout-latency" and when >= datetime(2025, 6, 24, tzinfo=timezone.utc):
        return 0.021
    return normal


def main() -> None:
    rng = random.Random(20250602)
    out = Path(__file__).with_name("events.csv")
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["timestamp", "slo", "good", "total"])
        for hour in range(HOURS):
            when = START + timedelta(hours=hour)
            daily = 0.55 + 0.45 * math.sin(2 * math.pi * (when.hour - 9) / 24.0)
            weekend = 0.7 if when.weekday() >= 5 else 1.0
            for slo, (peak, normal) in SLOS.items():
                total = int(peak * daily * weekend * rng.uniform(0.93, 1.07)) + 50
                ratio = failure_ratio(slo, when, normal) * rng.uniform(0.7, 1.3)
                bad = min(total, round(total * ratio))
                writer.writerow([when.strftime("%Y-%m-%dT%H:%M:%SZ"), slo, total - bad, total])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
