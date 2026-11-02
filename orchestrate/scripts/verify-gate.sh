#!/usr/bin/env bash
# Parent gate before code review: every "Manual Verification" box in the task's
# outline/plan must be ticked or marked HUMAN-ONLY, with a screenshot on disk.
# Usage: verify-gate.sh <worktree>   (exit 1 lists what is still open)
set -euo pipefail
RPI="$(cd -P "$(dirname "$0")/../.." && pwd)/rpilayer.py"
STATE=$(cd "$1" && python3 "$RPI" state)
# Outline/plan files come from rpilayer's own artifact list: their numbers vary by track.
DOCS=$(echo "$STATE" | python3 -c '
import json, sys
s = json.load(sys.stdin)
if s.get("error"): sys.exit("rpilayer state error: " + s["error"])
docs = [s["task_dir"] + "/" + a["file"] for a in s["artifacts"] if a["kind"] in ("structure-outline", "plan")]
if not docs: sys.exit("No outline or plan in " + s["task_dir"])
print(s["task_dir"]); print("\n".join(docs))
') || exit 1
TD=$(echo "$DOCS" | head -1)
docs=()
while IFS= read -r doc; do docs+=("$doc"); done < <(echo "$DOCS" | tail -n +2)
open=$(awk 'FNR==1{f=0} /^#+ *Manual Verification/{f=1;next} /^#/{f=0} f && /^[[:space:]]*- \[ \]/ && !/HUMAN-ONLY:/' "${docs[@]}")
shots=$( (find "$TD/verification" -name "*.png" 2>/dev/null || true) | wc -l | tr -d " " || true)
if [ -n "$open" ]; then echo "OPEN manual checks:"; echo "$open"; exit 1; fi
[ "$shots" -gt 0 ] || { echo "No screenshots in $TD/verification"; exit 1; }
echo "OK: all manual checks done or HUMAN-ONLY ($shots screenshots)"
