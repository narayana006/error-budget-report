import io
from datetime import datetime, timezone

import pytest

from error_budget_report.events import EventFileError, read_events

HEADER = "timestamp,slo,good,total\n"


def parse(body, header=HEADER):
    return read_events(io.StringIO(header + body))


def test_reads_and_sorts_buckets_per_slo():
    events = parse(
        "2025-06-02T01:00:00Z,api,90,100\n"
        "2025-06-02T00:00:00Z,api,99,100\n"
        "2025-06-02,web,5,5\n"
    )
    assert set(events) == {"api", "web"}
    assert [b.good for b in events["api"]] == [99, 90]
    assert events["api"][1].bad == 10
    assert events["web"][0].time == datetime(2025, 6, 2, tzinfo=timezone.utc)


def test_rows_with_the_same_timestamp_are_summed():
    events = parse("2025-06-02,api,40,50\n2025-06-02,api,45,50\n")
    (bucket,) = events["api"]
    assert (bucket.good, bucket.total) == (85, 100)


def test_timezones_are_normalised_to_utc():
    events = parse("2025-06-02T02:00:00+02:00,api,1,1\n")
    assert events["api"][0].time == datetime(2025, 6, 2, tzinfo=timezone.utc)


def test_column_order_and_extra_columns():
    events = parse("9,eu,api,2025-06-02,10\n", header="Good,region,SLO,Timestamp,Total\n")
    assert events["api"][0].total == 10


@pytest.mark.parametrize(
    "row, message",
    [
        ("monday,api,1,2", "line 2: timestamp"),
        ("2025-06-02,api,x,2", "line 2: good"),
        ("2025-06-02,api,1,-2", "non-negative"),
        ("2025-06-02,api,3,2", "larger than total"),
        ("2025-06-02,,1,2", "slo is empty"),
    ],
)
def test_bad_rows_name_the_line(row, message):
    with pytest.raises(EventFileError, match=message):
        parse(row + "\n")


def test_missing_column_and_empty_file():
    with pytest.raises(EventFileError, match="total"):
        parse("", header="timestamp,slo,good\n")
    with pytest.raises(EventFileError, match="empty"):
        read_events(io.StringIO(""))
