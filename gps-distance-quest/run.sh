#!/usr/bin/env bash
# One command: reproduce the dataset, the measurements, the QA tool output,
# the regression check (failing on v0, passing on v1) and the before/after numbers.
#   ./run.sh
# Requirements: Python 3.10+, pandas, numpy, pytest   (pip install -r requirements.txt)
set -uo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
mkdir -p evidence out
fail=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
expect() { # expect <wanted-exit> <label> <cmd...>
  local want=$1 label=$2; shift 2
  "$@"; local got=$?
  if [ "$got" -eq "$want" ]; then echo "  -> OK ($label: exit $got as expected)";
  else echo "  -> UNEXPECTED ($label: exit $got, wanted $want)"; fail=1; fi
}

step "1. Regenerate the synthetic dataset (seeded) and verify checksums"
$PY data/generate_dataset.py
expect 0 "dataset identical to committed copy" sha256sum -c data/SHA256SUMS

step "2. Measure and rank the three problems"
$PY analysis/measure_problems.py

step "3. QA tool on the ORIGINAL calculation (should FAIL: noise km billed)"
expect 1 "qa v0" $PY -m qa.noise_check --calc v0

step "4. QA tool on the FIXED calculation (should PASS)"
expect 0 "qa v1" $PY -m qa.noise_check --calc v1

step "5. Regression check on the ORIGINAL calculation (should FAIL)"
$PY -m pytest -q -p no:cacheprovider --impl=v0 2>&1 | tee evidence/regression_v0.txt | tail -12
expect 1 "pytest v0" test "${PIPESTATUS[0]}" -eq 0

step "6. Regression check on the FIXED calculation (should PASS)"
$PY -m pytest -q -p no:cacheprovider --impl=v1 2>&1 | tee evidence/regression_v1.txt | tail -4
expect 0 "pytest v1" test "${PIPESTATUS[0]}" -eq 0

step "7. Before vs after per driver per day"
expect 0 "before/after meets acceptance" $PY analysis/before_after.py

cp out/noise_by_driver_day_v0.csv out/noise_by_driver_day_v1.csv out/noise_pings_v0.csv evidence/ 2>/dev/null
step "SUMMARY"
if [ $fail -eq 0 ]; then echo "ALL EXPECTATIONS MET"; else echo "SOMETHING DID NOT BEHAVE AS EXPECTED - see above"; fi
exit $fail
