#!/usr/bin/env bash
# Exit (waking the parent) as soon as a child agent under <worktrees-dir> stops working or its terminal dies.
# Usage: monitor.sh <worktrees-dir>   (run it in the background; rerun after each wake-up)
# Fallback only: prefer SendMessage notify_when_idle, which needs no polling.
# ponytail: polls hc every 30s; switch to `hc events` if the latency matters.
B=$(cd "${1:?usage: monitor.sh <worktrees-dir>}" && pwd -P)
snap() {
  hc ls --all --json | python3 -c "
import json, sys
for t in json.load(sys.stdin)['terminals']:
    c = t.get('cwd', '')
    if c.startswith('$B/') and t.get('agent') == 'claude-code':
        print(t['address'], t.get('state'), t.get('status'), c.split('/')[-1])" | sort
}
prev=$(snap)
while sleep 30; do
  cur=$(snap)
  changed=$(diff <(echo "$prev") <(echo "$cur") | grep '^>' | grep -v ' working ' || true)
  if [ -n "$changed" ]; then echo "$changed"; exit 0; fi
  prev=$cur
done
