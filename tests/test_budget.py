from datetime import datetime, timedelta, timezone

import pytest

from error_budget_report import budget
from error_budget_report.events import Bucket
from error_budget_report.slo import SLO

T0 = datetime(2025, 6, 1, tzinfo=timezone.utc)
SLO_999 = SLO(name="api", target=0.999, window=timedelta(days=28), window_text="28d")
WEEK = ("7d", timedelta(days=7))
DAY = ("1d", timedelta(days=1))
HOUR = ("1h", timedelta(hours=1))


def daily(bad_per_day, total=100_000, days=28):
    """One bucket per day; bad_per_day is a number or a list with one entry per day."""
    bads = bad_per_day if isinstance(bad_per_day, list) else [bad_per_day] * days
    return [Bucket(T0 + timedelta(days=i), total - bad, total) for i, bad in enumerate(bads)]


def run(buckets, slo=SLO_999, as_of=None, burn=(DAY,), report=WEEK, **kwargs):
    as_of = as_of or T0 + timedelta(days=28)
    return budget.evaluate(slo, buckets, as_of, report, list(burn) + [report], **kwargs)


def test_budget_consumed_and_remaining():
    # 2.8M events at 99.9% allows 2,800 bad; 50/day for 28 days uses 1,400.
    r = run(daily(50))
    assert r.allowed_bad == pytest.approx(2800)
    assert r.budget_consumed == pytest.approx(0.5)
    assert r.budget_remaining == pytest.approx(0.5)
    assert r.compliance.sli == pytest.approx(0.9995)
    assert r.status == budget.HEALTHY
    assert not r.partial


def test_burn_rate_is_error_ratio_over_allowed_ratio():
    # Last day has 0.5% errors against a 0.1% allowance: 5x. The week averages (6*50+500)/700k.
    r = run(daily([50] * 27 + [500]))
    by_label = {w.label: w.burn_rate(SLO_999) for w in r.burn_windows}
    assert by_label["1d"] == pytest.approx(5.0)
    assert by_label["7d"] == pytest.approx((800 / 700_000) / 0.001)
    assert r.status == budget.BURNING


def test_report_window_spend_and_projection():
    r = run(daily([0] * 21 + [100] * 7))
    assert r.report.bad == 700
    assert r.budget_consumed_in_report == pytest.approx(700 / 2800)
    # 2,100 bad events of budget left at 100 per day.
    assert r.days_until_exhausted == pytest.approx(21.0)


def test_exhausted_budget():
    r = run(daily([0] * 20 + [3000] + [0] * 7))
    assert r.status == budget.EXHAUSTED
    assert r.budget_remaining < 0
    assert r.days_until_exhausted == 0.0


def test_exhausted_takes_priority_even_when_recent_burn_is_low():
    r = run(daily([3000] + [0] * 27))
    assert r.status == budget.EXHAUSTED
    assert r.report.burn_rate(SLO_999) == 0.0


def test_no_bad_events_never_runs_out():
    r = run(daily(0))
    assert r.budget_remaining == pytest.approx(1.0)
    assert r.days_until_exhausted is None
    assert r.worst_days == []


def test_window_boundaries_are_start_inclusive_end_exclusive():
    buckets = daily(10)
    as_of = T0 + timedelta(days=28)
    r = run(buckets + [Bucket(as_of, 0, 100_000)], as_of=as_of)  # bucket starting at as_of is excluded
    assert r.compliance.total == 2_800_000
    assert r.report.total == 700_000
    earlier = run(buckets, as_of=T0 + timedelta(days=10))
    assert earlier.compliance.total == 1_000_000  # nothing after as_of counted


def test_partial_data_is_flagged():
    r = run(daily(10, days=10), as_of=T0 + timedelta(days=10))
    assert r.partial
    assert r.days_of_data == pytest.approx(10.0)


def test_no_events_in_window_is_no_data():
    assert run([]).status == budget.NO_DATA
    old = [Bucket(T0 - timedelta(days=60), 9, 10)]
    r = run(old)
    assert r.status == budget.NO_DATA and r.budget_remaining is None


def test_burn_window_shorter_than_bucket_size_is_not_reported():
    r = run(daily(50), burn=(HOUR, DAY))
    by_label = {w.label: w for w in r.burn_windows}
    assert by_label["1h"].usable is False and by_label["1h"].burn_rate(SLO_999) is None
    assert by_label["1d"].burn_rate(SLO_999) == pytest.approx(0.5)


def test_worst_days_are_ranked_and_limited():
    r = run(daily([0] * 21 + [5, 400, 0, 90, 5, 5, 5]), top_days=2)
    assert [(d.day, d.bad) for d in r.worst_days] == [
        ((T0 + timedelta(days=22)).date(), 400),
        ((T0 + timedelta(days=24)).date(), 90),
    ]
    assert r.worst_days[0].share_of_budget == pytest.approx(400 / 2800)


def test_hourly_buckets_roll_up_into_days_and_short_windows():
    hours = [Bucket(T0 + timedelta(hours=h), 1000 - (20 if h == 47 else 0), 1000) for h in range(48)]
    slo = SLO(name="api", target=0.99, window=timedelta(days=2), window_text="2d")
    r = budget.evaluate(slo, hours, T0 + timedelta(days=2), DAY, [HOUR, DAY])
    assert r.burn_windows[0].burn_rate(slo) == pytest.approx(2.0)  # 2% errors vs 1% allowed
    assert r.worst_days[0].bad == 20 and r.worst_days[0].total == 24_000


def test_default_as_of_is_end_of_newest_bucket():
    events = {"a": daily(1, days=3), "b": [Bucket(T0 + timedelta(hours=h), 1, 1) for h in range(5)]}
    assert budget.default_as_of(events) == T0 + timedelta(days=2, hours=1)
    assert budget.default_as_of({"a": [Bucket(T0, 1, 1)]}) == T0 + timedelta(days=1)


def test_evaluate_all_orders_by_urgency():
    slos = [
        SLO("healthy", 0.999, timedelta(days=28), "28d"),
        SLO("missing", 0.999, timedelta(days=28), "28d"),
        SLO("gone", 0.999, timedelta(days=28), "28d"),
        SLO("burning", 0.999, timedelta(days=28), "28d"),
    ]
    events = {
        "healthy": daily(10),
        "gone": daily(200),
        "burning": daily([0] * 21 + [150] * 7),
    }
    reports = budget.evaluate_all(slos, events, T0 + timedelta(days=28), WEEK, [WEEK])
    assert [(r.slo.name, r.status) for r in reports] == [
        ("gone", budget.EXHAUSTED),
        ("burning", budget.BURNING),
        ("healthy", budget.HEALTHY),
        ("missing", budget.NO_DATA),
    ]
