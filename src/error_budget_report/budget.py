"""Error budget arithmetic.

Terms, for an SLO with target T over a rolling window W:

* allowed bad events = (1 - T) x total events in W          (the error budget)
* budget consumed    = bad events in W / allowed bad events
* burn rate over w   = (bad / total in w) / (1 - T)

A burn rate of 1 spends exactly one budget per SLO window; 2 spends it in half
the time. Every window ends at the report's "as of" time and includes buckets
whose timestamp t satisfies  as_of - w <= t < as_of.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Sequence

from .events import Bucket
from .slo import SLO

EXHAUSTED = "exhausted"
BURNING = "burning"  # budget left, but being spent faster than it is earned
HEALTHY = "healthy"
NO_DATA = "no data"


@dataclass(frozen=True)
class WindowStats:
    label: str
    length: timedelta
    good: float
    total: float
    usable: bool = True  # False when the window is shorter than the data's bucket size

    @property
    def bad(self) -> float:
        return self.total - self.good

    @property
    def sli(self) -> float | None:
        return self.good / self.total if self.total > 0 else None

    def burn_rate(self, slo: SLO) -> float | None:
        if not self.usable or self.total <= 0:
            return None
        return (self.bad / self.total) / slo.allowed_failure_ratio


@dataclass(frozen=True)
class DayCost:
    day: date
    bad: float
    total: float
    share_of_budget: float  # of the full SLO-window budget, 0-1+


@dataclass(frozen=True)
class SLOReport:
    slo: SLO
    status: str
    as_of: datetime
    compliance: WindowStats | None = None  # the SLO's own window
    report: WindowStats | None = None  # the reporting window (e.g. last 7d)
    burn_windows: list[WindowStats] = field(default_factory=list)
    allowed_bad: float = 0.0
    budget_consumed: float | None = None  # fraction of the budget spent in the SLO window
    budget_consumed_in_report: float | None = None  # fraction of the budget spent in the report window
    days_of_data: float = 0.0  # how much of the SLO window the data actually covers
    days_until_exhausted: float | None = None  # at the report window's rate of bad events
    worst_days: list[DayCost] = field(default_factory=list)

    @property
    def budget_remaining(self) -> float | None:
        return None if self.budget_consumed is None else 1.0 - self.budget_consumed

    @property
    def partial(self) -> bool:
        """True when the data does not span the whole SLO window."""
        return self.days_of_data < self.slo.window.total_seconds() / 86400.0 - 1e-9


def _stats(buckets: Sequence[Bucket], as_of: datetime, length: timedelta, label: str,
           usable: bool = True) -> WindowStats:
    start = as_of - length
    inside = [b for b in buckets if start <= b.time < as_of]
    return WindowStats(label, length, sum(b.good for b in inside), sum(b.total for b in inside), usable)


def bucket_size(buckets: Sequence[Bucket]) -> timedelta | None:
    """Smallest gap between consecutive buckets, taken as the data's resolution."""
    gaps = [b.time - a.time for a, b in zip(buckets, buckets[1:])]
    return min(gaps) if gaps else None


def default_as_of(events: dict[str, list[Bucket]]) -> datetime:
    """End of the newest bucket across all SLOs (its timestamp plus one bucket size)."""
    latest = max(buckets[-1].time for buckets in events.values() if buckets)
    sizes = [size for size in (bucket_size(b) for b in events.values()) if size]
    return latest + (min(sizes) if sizes else timedelta(days=1))


def evaluate(
    slo: SLO,
    buckets: Sequence[Bucket],
    as_of: datetime,
    report_window: tuple[str, timedelta],
    burn_windows: Sequence[tuple[str, timedelta]] = (),
    top_days: int = 3,
) -> SLOReport:
    compliance = _stats(buckets, as_of, slo.window, slo.window_text)
    if compliance.total <= 0:
        return SLOReport(slo=slo, status=NO_DATA, as_of=as_of)

    resolution = bucket_size(buckets)
    report = _stats(buckets, as_of, report_window[1], report_window[0])
    burns = [
        _stats(buckets, as_of, length, label, usable=resolution is None or length >= resolution)
        for label, length in burn_windows
    ]

    allowed = slo.allowed_failure_ratio * compliance.total
    consumed = compliance.bad / allowed
    in_window = [b for b in buckets if as_of - slo.window <= b.time < as_of]
    covered = (as_of - in_window[0].time).total_seconds() / 86400.0

    remaining_events = allowed - compliance.bad
    report_days = report_window[1].total_seconds() / 86400.0
    bad_per_day = report.bad / report_days
    days_left = None
    if remaining_events <= 0:
        days_left = 0.0
    elif bad_per_day > 0:
        days_left = remaining_events / bad_per_day

    report_burn = report.burn_rate(slo)
    if remaining_events <= 0:
        status = EXHAUSTED
    elif report_burn is not None and report_burn > 1.0:
        status = BURNING
    else:
        status = HEALTHY

    per_day: dict[date, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for b in buckets:
        if as_of - report_window[1] <= b.time < as_of:
            per_day[b.time.date()][0] += b.bad
            per_day[b.time.date()][1] += b.total
    worst = sorted(
        (DayCost(day, bad, total, bad / allowed) for day, (bad, total) in per_day.items() if bad > 0),
        key=lambda d: (-d.bad, d.day),
    )[: max(top_days, 0)]

    return SLOReport(
        slo=slo, status=status, as_of=as_of, compliance=compliance, report=report,
        burn_windows=burns, allowed_bad=allowed, budget_consumed=consumed,
        budget_consumed_in_report=report.bad / allowed, days_of_data=covered,
        days_until_exhausted=days_left, worst_days=worst,
    )


_STATUS_ORDER = {EXHAUSTED: 0, BURNING: 1, HEALTHY: 2, NO_DATA: 3}


def evaluate_all(
    slos: Sequence[SLO],
    events: dict[str, list[Bucket]],
    as_of: datetime,
    report_window: tuple[str, timedelta],
    burn_windows: Sequence[tuple[str, timedelta]] = (),
    top_days: int = 3,
) -> list[SLOReport]:
    """Evaluate every SLO; least budget remaining first."""
    reports = [
        evaluate(slo, events.get(slo.name, []), as_of, report_window, burn_windows, top_days)
        for slo in slos
    ]
    reports.sort(
        key=lambda r: (
            _STATUS_ORDER[r.status],
            r.budget_remaining if r.budget_remaining is not None else 0.0,
            r.slo.name,
        )
    )
    return reports
