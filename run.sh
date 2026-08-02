#!/usr/bin/env bash
# Cross-framework benchmark runner.
#
#   ./run.sh build                  build all nine frameworks x four apps
#   ./run.sh all                    build + calibrate + one full matrix round
#   ./run.sh measure <fw> <app>     one cell (e.g. ./run.sh measure lumen forms)
#   ./run.sh validate               calibrate + two full rounds + agreement table
#   ./run.sh report                 re-render results.md from results.json
#
# Sample counts, statistics thresholds and output paths are environment
# variables; see the Configuration section of README.md.
#
# All cargo builds (including the Lumen framework's lumenc) use a separate
# target dir so a shared Lumen target is never touched.
set -euo pipefail

cd "$(dirname "$0")"

# A shell may export a global CARGO_TARGET_DIR pointing at a shared Lumen
# target; building into it from here would poison its fingerprints. Point
# cargo at the suite's own target dir instead. bench.py owns the default
# (repo-local, gitignored); override BENCH_CARGO_TARGET_DIR to relocate.
export BENCH_CARGO_TARGET_DIR="${BENCH_CARGO_TARGET_DIR:-$PWD/harness/out/cargo-target}"
export CARGO_TARGET_DIR="$BENCH_CARGO_TARGET_DIR"

# Path to the Lumen framework checkout. If it is absent, the lumen rows
# are skipped with a note. Default: a Lumen dir beside this repo.
export LUMEN_REPO="${LUMEN_REPO:-$PWD/../Lumen}"

exec python3 harness/bench.py "${@:-all}"
