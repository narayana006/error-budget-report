"""Render SLO reports as Markdown or self-contained HTML."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape
from typing import Sequence

from .budget import BURNING, EXHAUSTED, HEALTHY, NO_DATA, SLOReport


def _pct(fraction: float | None, digits: int = 1) -> str:
    return "n/a" if fraction is None else f"{fraction * 100:.{digits}f}%"


def _target(target: float) -> str:
    return f"{target * 100:.4f}".rstrip("0").rstrip(".") + "%"


def _sli(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.3f}%"


def _count(value: float) -> str:
    return f"{value:,.0f}" if abs(value - round(value)) < 1e-6 else f"{value:,.1f}"


def _burn(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _when(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _days(value: float | None) -> str:
    if value is None:
        return "not at this rate"
    if value <= 0:
        return "already exhausted"
    return f"about {value:.1f} days" if value < 10 else f"about {value:.0f} days"


def _summary(reports: Sequence[SLOReport]) -> str:
    counts = Counter(r.status for r in reports)
    parts = [f"{counts[s]} {s}" for s in (EXHAUSTED, BURNING, HEALTHY, NO_DATA) if counts[s]]
    return f"{len(reports)} SLO(s): " + ", ".join(parts)


def _burn_labels(reports: Sequence[SLOReport]) -> list[str]:
    for r in reports:
        if r.burn_windows:
            return [w.label for w in r.burn_windows]
    return []


def _overview_rows(reports: Sequence[SLOReport], labels: Sequence[str]) -> list[list[str]]:
    rows = []
    for r in reports:
        if r.status == NO_DATA:
            rows.append([r.slo.name, r.slo.service or "-", _target(r.slo.target), r.slo.window_text,
                         "n/a", "n/a", "n/a", *["n/a"] * len(labels), r.status])
            continue
        rows.append([
            r.slo.name, r.slo.service or "-", _target(r.slo.target), r.slo.window_text,
            _sli(r.compliance.sli), _pct(r.budget_remaining), _pct(r.budget_consumed_in_report),
            *[_burn(w.burn_rate(r.slo)) for w in r.burn_windows], r.status,
        ])
    return rows


def _detail_lines(r: SLOReport) -> list[str]:
    """Plain-text sentences describing one SLO; shared by both formats."""
    if r.status == NO_DATA:
        return [f"No events found for this SLO in the {r.slo.window_text} before {_when(r.as_of)}."]
    lines = [
        f"Objective: {_target(r.slo.target)} of events good over a rolling {r.slo.window_text}. "
        f"Measured: {_sli(r.compliance.sli)} ({_count(r.compliance.good)} good of {_count(r.compliance.total)}).",
        f"Budget: {_count(r.allowed_bad)} bad events allowed, {_count(r.compliance.bad)} used "
        f"({_pct(r.budget_consumed)} consumed, {_pct(r.budget_remaining)} remaining).",
        f"Last {r.report.label}: {_count(r.report.bad)} bad of {_count(r.report.total)} events "
        f"(SLI {_sli(r.report.sli)}), which spent {_pct(r.budget_consumed_in_report)} of the budget "
        f"at a burn rate of {_burn(r.report.burn_rate(r.slo))}.",
    ]
    if r.status != EXHAUSTED:
        lines.append(f"Budget runs out in: {_days(r.days_until_exhausted)} if the last {r.report.label} repeats.")
    if r.partial:
        lines.append(
            f"Note: data covers only {r.days_of_data:.1f} days of the {r.slo.window_text} window, "
            "so the budget is computed on what is available."
        )
    return lines


def _worst_day_text(r: SLOReport) -> list[str]:
    return [
        f"{d.day}: {_count(d.bad)} bad of {_count(d.total)} events, {_pct(d.share_of_budget)} of the budget"
        for d in r.worst_days
    ]


def to_markdown(reports: Sequence[SLOReport], as_of: datetime, window_label: str) -> str:
    labels = _burn_labels(reports)
    header = ["SLO", "Service", "Target", "Window", "SLI", "Budget left", f"Spent in {window_label}",
              *[f"Burn {label}" for label in labels], "Status"]
    lines = [
        "# Error budget report",
        "",
        f"As of {_when(as_of)}, reporting window {window_label}. {_summary(reports)}.",
        "",
        "| " + " | ".join(header) + " |",
        "|---|---|---:|---:|---:|---:|---:|" + "---:|" * len(labels) + "---|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in _overview_rows(reports, labels)]
    lines.append("")
    for r in reports:
        lines += [f"## {r.slo.title} ({r.status})", ""]
        if r.slo.description:
            lines += [r.slo.description, ""]
        lines += [f"- {line}" for line in _detail_lines(r)]
        if r.worst_days:
            lines += ["", f"Days that cost the most budget in the last {window_label}:", ""]
            lines += [f"- {text}" for text in _worst_day_text(r)]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


_CSS = """
body{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:#1c2330;max-width:980px;margin:2rem auto;padding:0 1rem}
h1{margin-bottom:.2rem} .meta{color:#5b6472;margin-top:0}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:14px}
th,td{padding:.4rem .6rem;border-bottom:1px solid #e3e6eb;text-align:right;white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
.badge{display:inline-block;padding:.05rem .5rem;border-radius:1rem;font-size:12px;font-weight:600;color:#fff}
.exhausted{background:#b42318}.burning{background:#b54708}.healthy{background:#067647}.no-data{background:#667085}
section{border:1px solid #e3e6eb;border-radius:8px;padding:.2rem 1rem 1rem;margin:1rem 0}
.bar{height:10px;background:#e3e6eb;border-radius:5px;overflow:hidden;margin:.4rem 0 .8rem}
.bar span{display:block;height:100%}
.desc{color:#5b6472}
""".strip()


def _badge(status: str) -> str:
    return f'<span class="badge {status.replace(" ", "-")}">{escape(status)}</span>'


def to_html(reports: Sequence[SLOReport], as_of: datetime, window_label: str) -> str:
    labels = _burn_labels(reports)
    header = ["SLO", "Service", "Target", "Window", "SLI", "Budget left", f"Spent in {window_label}",
              *[f"Burn {label}" for label in labels], "Status"]
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>Error budget report, {escape(as_of.strftime('%Y-%m-%d'))}</title>",
        f"<style>{_CSS}</style></head><body>",
        "<h1>Error budget report</h1>",
        f'<p class="meta">As of {escape(_when(as_of))}, reporting window {escape(window_label)}. '
        f"{escape(_summary(reports))}.</p>",
        "<table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in header) + "</tr></thead><tbody>",
    ]
    for row in _overview_rows(reports, labels):
        cells = [f"<td>{escape(cell)}</td>" for cell in row[:-1]] + [f"<td>{_badge(row[-1])}</td>"]
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    for r in reports:
        out.append(f"<section><h2>{escape(r.slo.title)} {_badge(r.status)}</h2>")
        if r.slo.description:
            out.append(f'<p class="desc">{escape(r.slo.description)}</p>')
        if r.budget_remaining is not None:
            width = min(max(r.budget_remaining, 0.0), 1.0) * 100
            out.append(
                f'<div class="bar" title="budget remaining"><span class="{r.status.replace(" ", "-")}" '
                f'style="width:{width:.1f}%"></span></div>'
            )
        out.append("<ul>" + "".join(f"<li>{escape(line)}</li>" for line in _detail_lines(r)) + "</ul>")
        if r.worst_days:
            out.append(f"<p>Days that cost the most budget in the last {escape(window_label)}:</p>")
            out.append("<ul>" + "".join(f"<li>{escape(t)}</li>" for t in _worst_day_text(r)) + "</ul>")
        out.append("</section>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"
