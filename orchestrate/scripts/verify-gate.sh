#!/usr/bin/env bash
# Parent gate before code review: every "Manual Verification" box in the task's
# outline/plan must be ticked or marked HUMAN-ONLY, with a screenshot on disk.
# Usage: verify-gate.sh <worktree>   (exit 1 lists what is still open)
set -euo pipefail
RPI="$(cd -P "$(dirname "$0")/../.." && pwd)/rpilayer.py"
STATE=$(cd "$1" && python3 "$RPI" state)
TD=$(echo "$STATE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["task_dir"])')
open=$(awk '/^#+ *Manual Verification/{f=1;next} /^#/{f=0} f && /^[[:space:]]*- \[ \]/ && !/HUMAN-ONLY:/' "$TD"/0[4-9]-*.md || true)
shots=$( (find "$TD/verification" -name "*.png" 2>/dev/null || true) | wc -l | tr -d " " || true)
if [ -n "$open" ]; then echo "OPEN manual checks:"; echo "$open"; exit 1; fi
[ "$shots" -gt 0 ] || { echo "No screenshots in $TD/verification"; exit 1; }
echo "OK: all manual checks done or HUMAN-ONLY ($shots screenshots)"
