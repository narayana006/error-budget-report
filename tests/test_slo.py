import json
from datetime import timedelta

import pytest

from error_budget_report.slo import SLOError, load_slos, parse_duration

OPENSLO = """
apiVersion: openslo/v1
kind: SLO
metadata:
  name: api-availability
  displayName: API availability
spec:
  description: >
    Requests answered
    without a 5xx.
  service: api
  budgetingMethod: Occurrences
  timeWindow:
    - duration: 28d
      isRolling: true
  objectives:
    - target: 0.999
"""


def write(tmp_path, text, name="slo.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_loads_openslo_document(tmp_path):
    (slo,) = load_slos(write(tmp_path, OPENSLO))
    assert slo.name == "api-availability"
    assert slo.title == "API availability"
    assert slo.service == "api"
    assert slo.target == pytest.approx(0.999)
    assert slo.window == timedelta(days=28) and slo.window_text == "28d"
    assert slo.description == "Requests answered without a 5xx."
    assert slo.allowed_failure_ratio == pytest.approx(0.001)


def test_target_percent_and_default_budgeting_method(tmp_path):
    text = OPENSLO.replace("target: 0.999", "targetPercent: 99.5").replace("  budgetingMethod: Occurrences\n", "")
    assert load_slos(write(tmp_path, text))[0].target == pytest.approx(0.995)


def test_other_kinds_are_skipped_in_multi_document_files(tmp_path):
    text = "apiVersion: openslo/v1\nkind: Service\nmetadata:\n  name: api\n---" + OPENSLO + "---\n"
    assert [s.name for s in load_slos(write(tmp_path, text))] == ["api-availability"]


def test_short_form_yaml_and_json(tmp_path):
    yaml_path = write(tmp_path, "slos:\n  - name: a\n    target: 0.99\n    window: 7d\n    service: web\n")
    (a,) = load_slos(yaml_path)
    assert (a.name, a.target, a.window, a.service, a.title) == ("a", 0.99, timedelta(days=7), "web", "a")
    json_path = write(tmp_path, json.dumps({"slos": [{"name": "b", "targetPercent": 95, "window": "12h"}]}), "b.json")
    (b,) = load_slos(json_path)
    assert b.target == pytest.approx(0.95) and b.window == timedelta(hours=12)


def test_directory_loads_all_files_sorted_and_ignores_others(tmp_path):
    write(tmp_path, OPENSLO, "b.yaml")
    write(tmp_path, "slos:\n  - {name: first, target: 0.9, window: 1d}\n", "a.yml")
    write(tmp_path, "not an slo", "notes.txt")
    assert [s.name for s in load_slos(str(tmp_path))] == ["first", "api-availability"]


def test_duplicate_names_are_rejected(tmp_path):
    write(tmp_path, OPENSLO, "a.yaml")
    write(tmp_path, OPENSLO, "b.yaml")
    with pytest.raises(SLOError, match="defined in both"):
        load_slos(str(tmp_path))


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("budgetingMethod: Occurrences", "budgetingMethod: Timeslices", "Timeslices"),
        ("isRolling: true", "isRolling: false", "calendar-aligned"),
        ("duration: 28d", "duration: 1M", "not supported"),
        ("target: 0.999", "target: 99.9", "between 0 and 1"),
        ("target: 0.999", "target: high", "must be a number"),
        ("    - target: 0.999", "    - target: 0.999\n    - target: 0.99", "exactly one objective"),
        ("  name: api-availability\n", "", "metadata.name"),
        ("    - target: 0.999", "    - displayName: x", "no target"),
    ],
)
def test_unsupported_or_invalid_openslo(tmp_path, old, new, message):
    assert old in OPENSLO
    with pytest.raises(SLOError, match=message):
        load_slos(write(tmp_path, OPENSLO.replace(old, new)))


def test_missing_paths_empty_dirs_and_bad_yaml(tmp_path):
    with pytest.raises(SLOError, match="no such file"):
        load_slos(str(tmp_path / "nope"))
    with pytest.raises(SLOError, match="no .yaml"):
        load_slos(str(tmp_path))
    with pytest.raises(SLOError, match="cannot parse"):
        load_slos(write(tmp_path, "a: [unclosed"))
    with pytest.raises(SLOError, match="no SLO definitions"):
        load_slos(write(tmp_path, "kind: Service\nmetadata: {name: x}\n", "svc.yaml"))


@pytest.mark.parametrize("text, expected", [
    ("30m", timedelta(minutes=30)), ("6h", timedelta(hours=6)),
    ("7d", timedelta(days=7)), ("4w", timedelta(weeks=4)),
])
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "7", "d", "1M", "1.5d", "0d", "-1d", "7 days"])
def test_parse_duration_rejects(text):
    with pytest.raises(ValueError):
        parse_duration(text)
