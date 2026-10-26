#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs one GitHub Actions step script; if it fails, its last lines become an annotation on the run,
# so a failure can be read from the run's summary even where the full job log can't be reached.
#   (workflow)  defaults: run: shell: bash /tmp/ci-step.sh {0}
log=$(mktemp)
bash --noprofile --norc -eo pipefail "$1" 2>&1 | tee "$log"
code=${PIPESTATUS[0]}
if [ "$code" -ne 0 ]; then
  msg=$(tail -n 25 "$log" | cut -c1-200 | sed 's/%/%25/g' | awk '{printf "%s%%0A", $0}')
  echo "::error title=Step failed (exit $code)::$msg"
fi
rm -f "$log"
exit "$code"
