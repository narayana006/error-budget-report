import io
from pathlib import Path

import pytest

from error_budget_report.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SLOS = str(EXAMPLES / "slos")
EVENTS = str(EXAMPLES / "events.csv")
BASE = ["--slos", SLOS, "--events", EVENTS]


def test_markdown_report_on_examples(capsys):
    assert main(BASE + ["--window", "7d"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Error budget report")
    assert "As of 2025-06-30 00:00 UTC, reporting window 7d. 4 SLO(s): 1 exhausted, 1 burning, 2 healthy." in out
    assert "| Burn 1h | Burn 6h | Burn 1d | Burn 7d | Status |" in out
    rows = [line.split(" | ") for line in out.splitlines() if line.startswith("| ") and "SLO" not in line]
    assert [(r[0].lstrip("| "), r[-1].rstrip(" |")) for r in rows] == [
        ("checkout-availability", "exhausted"),
        ("checkout-latency", "burning"),
        ("notifications-delivery", "healthy"),
        ("search-availability", "healthy"),
    ]
    assert "## Checkout availability (exhausted)" in out
    assert "- 2025-06-26:" in out


def test_html_report_is_self_contained_and_escaped(tmp_path, capsys):
    slos = tmp_path / "slos.yaml"
    slos.write_text(
        "slos:\n  - name: checkout-availability\n    description: 'a <b>bold</b> & risky claim'\n"
        "    target: 0.999\n    window: 28d\n"
    )
    target = tmp_path / "report.html"
    assert main(["--slos", str(slos), "--events", EVENTS, "--format", "html", "--output", str(target)]) == 0
    html = target.read_text()
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "a &lt;b&gt;bold&lt;/b&gt; &amp; risky claim" in html
    assert '<span class="badge exhausted">exhausted</span>' in html
    assert "http" not in html  # no external assets
    assert "unknown SLO 'search-availability'" in capsys.readouterr().err


def test_as_of_moves_every_window(capsys):
    assert main(BASE + ["--as-of", "2025-06-20T00:00:00Z"]) == 0
    out = capsys.readouterr().out
    assert "As of 2025-06-20 00:00 UTC" in out
    assert "exhausted" not in out  # the bad deploy on 2025-06-26 has not happened yet
    assert "data covers only 18.0 days of the 28d window" in out


def test_custom_windows(capsys):
    assert main(BASE + ["--window", "3d", "--burn-windows", "12h,2h", "--top-days", "1"]) == 0
    out = capsys.readouterr().out
    assert "| Spent in 3d | Burn 2h | Burn 12h | Burn 3d | Status |" in out
    assert out.count("\n- 2025-06-") == 4  # one worst day per SLO


def test_fail_on_exhausted(capsys):
    assert main(BASE + ["--fail-on-exhausted"]) == 2
    assert main(BASE + ["--fail-on-exhausted", "--as-of", "2025-06-20"]) == 0


def test_events_from_stdin_and_slo_without_events(monkeypatch, capsys):
    rows = "timestamp,slo,good,total\n" + "".join(
        f"2025-06-{d:02d},search-availability,999,1000\n" for d in range(1, 29)
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(rows))
    assert main(["--slos", SLOS, "--events", "-"]) == 0
    out = capsys.readouterr().out
    assert "1 healthy, 3 no data" in out
    assert "| Burn 1h |" in out and "| n/a | n/a | 0.20x | 0.20x | healthy |" in out


@pytest.mark.parametrize(
    "args, message",
    [
        (["--slos", "/no/such/dir", "--events", EVENTS], "no such file or directory"),
        (["--slos", SLOS, "--events", "/no/such/file.csv"], "No such file"),
        (BASE + ["--window", "1M"], "not supported"),
        (BASE + ["--burn-windows", "soon"], "not supported"),
        (BASE + ["--as-of", "yesterday"], "not an ISO 8601 timestamp"),
    ],
)
def test_errors_exit_1_with_message(args, message, capsys):
    assert main(args) == 1
    assert message in capsys.readouterr().err
