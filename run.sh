#!/usr/bin/env bash
# Cross-framework benchmark runner.
#
#   ./run.sh build     build all six apps + record binary sizes
#   ./run.sh measure   run startup/scroll/RSS measurements headlessly
#   ./run.sh all       build + measure + write results.md / results.json
#
# All cargo builds (including the Lumen framework's lumenc) use a private
# target dir so the Lumen repo's shared target is never touched.
set -euo pipefail

# Hard-forced: the developer shell exports a global CARGO_TARGET_DIR that
# points at the Lumen repo's shared target dir; building into it from here
# would poison its fingerprints. Override BENCH_CARGO_TARGET_DIR to relocate.
export CARGO_TARGET_DIR="${BENCH_CARGO_TARGET_DIR:-/Storage/cargo-target-benchcomp}"
export LUMEN_REPO="${LUMEN_REPO:-/home/artur/Lumen}"

cd "$(dirname "$0")"
exec python3 harness/bench.py "${@:-all}"
