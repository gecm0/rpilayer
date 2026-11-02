#!/usr/bin/env bash
# Advance a child to its next rpilayer step with a real /clear.
# Usage: ORCHESTRATE_PARENT=<parent session> advance.sh <terminal> <worktree> [message]   (message defaults to /rpilayer)
# Prints the rpilayer state; refuses to advance while design questions are open.
set -euo pipefail
RPI="$(cd -P "$(dirname "$0")/../.." && pwd)/rpilayer.py"
T=$1; W=$2; MSG=${3:-/rpilayer}
PARENT=${ORCHESTRATE_PARENT:?set ORCHESTRATE_PARENT to your session name}
BRIEF="$(cd -P "$(dirname "$0")/.." && pwd)/child-brief.md"
STATE=$(cd "$W" && python3 "$RPI" state)
echo "$STATE" | python3 -c '
import json, sys
s = json.load(sys.stdin)
if s.get("error"): print("rpilayer state error:", s["error"]); sys.exit(5)
print("next:", s.get("next"), "| open design questions:", s.get("open_design_questions"), "| latest:", s.get("latest"))
sys.exit(3 if (s.get("open_design_questions") or 0) > 0 else 0)
' || { rc=$?; [ $rc -eq 3 ] && echo "STOP: open design questions, needs Germán" || echo "STOP: no usable rpilayer state, nothing sent"; exit $rc; }
# Code review only after every manual check ran in a browser (verify-gate.sh).
if [[ "$MSG" == *open-code-review* ]]; then
  "$(dirname "$0")/verify-gate.sh" "$W" || { echo "STOP: browser verification incomplete, send the child back to it"; exit 4; }
fi
# hc send wraps text in <hc> tags, so /clear must be typed as keys to run as a command.
hc keys "$T" / c l e a r enter >/dev/null
hc wait "$T" --timeout 60 >/dev/null || true
# /clear drops the launch message, so the child must reload its rules and its parent's name.
hc send "$T" "Re-read $BRIEF and follow it for the rest of this ticket. Your parent session is $PARENT. Reply only: ok" --wait --timeout 120 >/dev/null || true
hc send "$T" "$MSG" >/dev/null
echo "sent to $T: $MSG"
