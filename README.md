# error-budget-report

Turn SLO definitions and good/total event counts into an error budget report: how much budget is left, how fast it is burning, and which days spent it.

**Status:** early but working. Today it reads SLO definitions from YAML or JSON (a documented subset of OpenSLO v1, or a short form), reads event counts from a CSV, computes budget remaining and burn rate over several windows, and writes a Markdown or HTML report. It does not query Prometheus or Datadog, does not link budget spend to incidents or deploys, and does not post or schedule anything. See the [checklist](#features).

## Install

Requires Python 3.10 or newer. One dependency: PyYAML.

```bash
git clone https://github.com/narayana006/error-budget-report
cd error-budget-report
python -m pip install .
```

## Quick start

The [`examples/`](examples) directory has four SLO definitions and 28 days of synthetic hourly counts.

```bash
error-budget-report --slos examples/slos --events examples/events.csv --window 7d
```

Output:

```markdown
# Error budget report

As of 2025-06-30 00:00 UTC, reporting window 7d. 4 SLO(s): 1 exhausted, 1 burning, 2 healthy.

| SLO | Service | Target | Window | SLI | Budget left | Spent in 7d | Burn 1h | Burn 6h | Burn 1d | Burn 7d | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| checkout-availability | checkout | 99.9% | 28d | 99.879% | -21.2% | 87.0% | 0.32x | 0.43x | 0.40x | 3.47x | exhausted |
| checkout-latency | checkout | 99% | 28d | 99.242% | 24.2% | 45.7% | 1.59x | 1.86x | 2.06x | 1.82x | burning |
| notifications-delivery | notifications | 99% | 14d | 99.704% | 70.4% | 14.7% | 0.29x | 0.30x | 0.31x | 0.29x | healthy |
| search-availability | search | 99.5% | 28d | 99.879% | 75.9% | 5.9% | 0.20x | 0.25x | 0.24x | 0.23x | healthy |

## Checkout availability (exhausted)

Checkout API requests answered without a 5xx.

- Objective: 99.9% of events good over a rolling 28d. Measured: 99.879% (14,214,951 good of 14,232,194).
- Budget: 14,232.2 bad events allowed, 17,243 used (121.2% consumed, -21.2% remaining).
- Last 7d: 12,377 bad of 3,562,376 events (SLI 99.653%), which spent 87.0% of the budget at a burn rate of 3.47x.

Days that cost the most budget in the last 7d:

- 2025-06-26: 11,179 bad of 549,056 events, 78.5% of the budget
- 2025-06-27: 234 bad of 561,566 events, 1.6% of the budget
- 2025-06-24: 229 bad of 559,842 events, 1.6% of the budget

## Checkout latency (burning)

Checkout API requests answered within 400 ms.

- Objective: 99% of events good over a rolling 28d. Measured: 99.242% (14,121,455 good of 14,229,363).
- Budget: 142,293.6 bad events allowed, 107,908 used (75.8% consumed, 24.2% remaining).
- Last 7d: 65,042 bad of 3,565,059 events (SLI 98.176%), which spent 45.7% of the budget at a burn rate of 1.82x.
- Budget runs out in: about 3.7 days if the last 7d repeats.

Days that cost the most budget in the last 7d:

- 2025-06-24: 12,128 bad of 558,771 events, 8.5% of the budget
- 2025-06-26: 11,846 bad of 551,250 events, 8.3% of the budget
- 2025-06-27: 11,704 bad of 564,428 events, 8.2% of the budget

## notifications-delivery (healthy)

Push notifications accepted by the provider.

- Objective: 99% of events good over a rolling 14d. Measured: 99.704% (1,534,459 good of 1,539,019).
- Budget: 15,390.2 bad events allowed, 4,560 used (29.6% consumed, 70.4% remaining).
- Last 7d: 2,255 bad of 769,397 events (SLI 99.707%), which spent 14.7% of the budget at a burn rate of 0.29x.
- Budget runs out in: about 34 days if the last 7d repeats.

Days that cost the most budget in the last 7d:

- 2025-06-24: 368 bad of 120,495 events, 2.4% of the budget
- 2025-06-26: 360 bad of 119,852 events, 2.3% of the budget
- 2025-06-27: 350 bad of 119,407 events, 2.3% of the budget

## Search availability (healthy)

Search queries that return a result page.

- Objective: 99.5% of events good over a rolling 28d. Measured: 99.879% (39,864,651 good of 39,912,831).
- Budget: 199,564.2 bad events allowed, 48,180 used (24.1% consumed, 75.9% remaining).
- Last 7d: 11,689 bad of 9,951,334 events (SLI 99.883%), which spent 5.9% of the budget at a burn rate of 0.23x.
- Budget runs out in: about 91 days if the last 7d repeats.

Days that cost the most budget in the last 7d:

- 2025-06-25: 1,884 bad of 1,551,674 events, 0.9% of the budget
- 2025-06-27: 1,872 bad of 1,547,680 events, 0.9% of the budget
- 2025-06-26: 1,794 bad of 1,535,279 events, 0.9% of the budget
```

For a self-contained HTML page (inline CSS, no external assets) with the same content:

```bash
error-budget-report --slos examples/slos --events examples/events.csv --format html --output report.html
```

## What the numbers mean

For an SLO with target T over a rolling window W, ending at the report's "as of" time:

| Term | Definition |
|---|---|
| SLI | good events / total events in W |
| Error budget | (1 - T) x total events in W, i.e. the number of bad events allowed |
| Budget left | 1 - (bad events in W / error budget). Negative when overspent |
| Spent in 7d | bad events in the reporting window / error budget |
| Burn rate over w | (bad / total in w) / (1 - T). At 1x the budget lasts exactly one SLO window; at 2x, half of one |
| Budget runs out in | budget left, in events, divided by bad events per day in the reporting window |

Status is `exhausted` when no budget is left, `burning` when budget is left but the reporting window's burn rate is above 1x, `healthy` otherwise, and `no data` when the SLO has no events in its window. SLOs are listed most urgent first.

A window covers buckets with `as_of - w <= timestamp < as_of`. By default "as of" is the end of the newest bucket in the events file; set it with `--as-of` to reproduce a past report. A burn window shorter than the spacing of your data (for example `1h` with daily counts) is shown as `n/a` rather than guessed.

## Event counts CSV

A header row is required. Column order does not matter, names are case-insensitive, extra columns are ignored.

| Column | Meaning |
|---|---|
| `timestamp` | Start of the bucket. ISO 8601 or a plain date; no zone means UTC |
| `slo` | SLO name, matching `metadata.name` in the definition |
| `good` | Events in the bucket that met the objective |
| `total` | All valid events in the bucket |

```csv
timestamp,slo,good,total
2025-06-02T00:00:00Z,checkout-availability,9158,9162
2025-06-02T00:00:00Z,checkout-latency,10172,10215
2025-06-02T00:00:00Z,search-availability,28082,28109
2025-06-02T00:00:00Z,notifications-delivery,2036,2041
```

Buckets can be any size (hourly and daily are typical) and rows with the same SLO and timestamp are added together. Rows for SLOs that have no definition are ignored with a warning on stderr. Use `--events -` to read from stdin. Getting these counts out of your metrics system is up to you for now.

## SLO definitions

`--slos` takes one file, or a directory whose `.yaml`, `.yml` and `.json` files are all read (not recursively). YAML files may hold several documents separated by `---`. SLO names must be unique.

### OpenSLO v1

```yaml
apiVersion: openslo/v1
kind: SLO
metadata:
  name: search-availability
  displayName: Search availability
spec:
  description: Search queries that return a result page.
  service: search
  budgetingMethod: Occurrences
  timeWindow:
    - duration: 28d
      isRolling: true
  objectives:
    - target: 0.995
```

Only part of OpenSLO is understood. The tool does not validate documents against the OpenSLO schema.

| OpenSLO field | Support |
|---|---|
| `kind: SLO` | Read. Documents of any other kind (`Service`, `SLI`, `DataSource`, `AlertPolicy`, ...) are skipped silently |
| `metadata.name` | Required. Used to match rows in the events CSV |
| `metadata.displayName` | Used as the section heading |
| `spec.service`, `spec.description` | Shown in the report |
| `spec.budgetingMethod` | `Occurrences` only (also the default if omitted). `Timeslices` and `RatioTimeslices` are rejected with an error |
| `spec.objectives` | Exactly one objective. `target` (0 to 1) or `targetPercent` (0 to 100) is read. More than one objective is an error |
| `spec.timeWindow` | Exactly one, rolling, with `duration` as a whole number of `m`, `h`, `d` or `w` (e.g. `28d`). Calendar-aligned windows (`isRolling: false` or `calendar:`) and the `M`, `Q`, `Y` units are rejected with an error |
| `spec.indicator`, `spec.indicatorRef` | Ignored. Queries are not executed; counts come from the CSV |
| `objectives[].op`, `value`, `timeSliceTarget`, `timeSliceWindow`, `compositeWeight` | Ignored |
| `spec.alertPolicies`, `metadata.labels`, `metadata.annotations` | Ignored |

### Short form

If you do not use OpenSLO, a file with a top-level `slos` list works too:

```yaml
# The short form: no OpenSLO envelope, just the fields the report needs.
slos:
  - name: notifications-delivery
    service: notifications
    description: Push notifications accepted by the provider.
    target: 0.99
    window: 14d
```

`name`, `window` and one of `target` / `targetPercent` are required; `service`, `description` and `displayName` are optional.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--slos PATH` | required | SLO file or directory |
| `--events FILE` | required | Event counts CSV, or `-` for stdin |
| `--window DURATION` | 7d | Reporting window |
| `--burn-windows LIST` | 1h,6h,1d | Extra burn-rate windows, comma-separated. The reporting window is always included |
| `--as-of TIMESTAMP` | end of newest bucket | End of every window |
| `--top-days N` | 3 | Worst days listed per SLO |
| `--format {markdown,html}` | markdown | Output format |
| `--output FILE` | stdout | Write the report to a file |
| `--fail-on-exhausted` | off | Exit with status 2 if any SLO has no budget left |

Durations are a whole number followed by `m`, `h`, `d` or `w`. Exit status is 0 on success and 1 for unreadable or invalid input.

## Features

- [x] Reads OpenSLO definitions (the subset in the table above)
- [ ] Computes budget remaining and burn rate from Prometheus or Datadog (the computation works today, but only from a CSV of counts; no metrics backend is queried)
- [ ] Links budget consumption to incidents and deploys in the window (today it only lists the days that cost the most)
- [x] Markdown or HTML report (posting to chat is not built)
- [ ] Scheduled weekly run (run it from cron or CI yourself)

## Limitations

- Counts must be exported to CSV by you. There are no Prometheus, Datadog or other backend adapters.
- Occurrence-based budgets only: no time-slice budgeting, no calendar-aligned windows, one objective per SLO.
- "Budget runs out in" is a simple projection from the reporting window's rate of bad events. It ignores older bad events dropping out of the rolling window, so it is pessimistic after a past incident and is not a forecast.
- If the events file covers less than the SLO window, the budget is computed on the data available and the report says so.
- Days in the "cost the most budget" list are UTC calendar days.
- No JSON output, no chat posting, no built-in scheduler.
- The example data is synthetic.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python examples/generate_sample.py   # regenerates the sample events deterministically
```

## Contributing

Issues and pull requests are welcome. Adapters that produce the events CSV from a metrics backend, and wider OpenSLO coverage, are the most useful next steps. Please include a test with any code change.

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
