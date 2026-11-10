# error-budget-report

Generate a weekly error budget report from your SLO definitions and metrics, with what consumed the budget.

> **Project status: planning. There is no working code in this repository yet.**
> This README describes what the project will do. Nothing below can be installed or run today.
> Features are ticked off in the checklist as they are built.

## What it is

A command-line tool.

**The problem it solves:** Error budgets only change decisions if people see them regularly and understand what spent them.

## Who it is for

Teams with SLOs who want error budgets to be seen and acted on.

## How it will work

1. You give the tool your SLO definitions and access to your metrics.
2. It computes how much budget is left and how fast it is burning.
3. It writes a weekly report that ties budget spent to the incidents and deploys that caused it.

## Planned features

Unticked items are not built yet.

- [ ] Reads OpenSLO definitions
- [ ] Computes budget remaining and burn rate from Prometheus or Datadog
- [ ] Links budget consumption to incidents and deploys in the window
- [ ] Markdown or HTML report, optionally posted to chat
- [ ] Scheduled weekly run

## Planned usage

This is the intended interface, shown so you can judge the design. **It does not work yet**, and names may change before the first release.

```bash
error-budget-report --slos ./slos --window 7d
```

## Contributing

Feedback on the design is the most useful contribution right now. Open an issue to suggest a feature, question an approach or describe your use case. Code contributions are welcome once the first version lands.

## Author

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
