# Contributing

Issues and pull requests are welcome. Open an issue first for a new framework,
a new app, or a change to how a metric is measured, since those affect every
row in the table.

## Building and verifying

Each framework needs its own toolchain; a missing one skips those rows instead
of failing the run. The harness needs Python 3 and a C compiler.

```sh
./run.sh build                  # build all frameworks x apps
./run.sh measure lumen forms    # one cell, for a quick check
python3 harness/test_stats.py   # statistics helpers
python3 harness/bench.py report # re-render results.md from results.json
```

Measurement runs happen under a nested headless compositor that the harness
starts itself; nothing opens on your desktop. CI builds every framework and
runs the harness tests, but measures nothing, so a shared runner never
produces numbers.

## Pull requests

Keep the comparison like for like. A change to one framework's app usually
needs the same change in the other seven; if it cannot be matched, add a caveat
to `results.md` instead of leaving the difference unstated.

Commit numbers only from a run that measured them, on one quiet machine, and
say which machine in the pull request. Do not hand-edit `results.json` or
`results.md`; regenerate them.
