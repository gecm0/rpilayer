# Child session: rules

You implement one ticket in your own git worktree, created by graft. A parent session orchestrates you; its session name and your ticket are in the message that pointed you here. These rules override conflicting defaults.

## First, once

1. Read the repo's worktree contract (the `AGENTS.md` section on worktrees, named in your task message). It says how your environment was set up, how to check it, how to restart it, how to start the UI and log in, and what is forbidden. Run its check now. If the check fails or a script prints ABORT, stop and report to the parent. Never work around it.
2. Run `/rpilayer`. Your task and its `ticket.md` already exist for this worktree.

## Never

- Never touch production: no `--prod`, deploys, deploy keys, release tags, or any read or write against a production system.
- Never touch shared environments (a shared dev database or deployment, another worktree's servers or ports). Your worktree has its own; use only that.
- Never pick ports or start servers by hand when the contract provides scripts for it.
- Never kill processes you did not start. A port taken by someone else: report it.

## Verification in a real browser

Node tests are not enough. Every phase's "Manual Verification" checks are executable by you: do them yourself, in a real browser, before that phase's commit.

1. Run `agent-browser skills get core` once.
2. Start your UI with the contract's command. Create the data each check needs in your own environment.
3. Use your own browser session (`agent-browser --session <ticket> ...`). Perform each check exactly as written and read the result (snapshot, `get text`, focus via `eval "document.activeElement..."`).
4. Save one screenshot per check in `<task_dir>/verification/phase-N-check-M.png`.
5. Tick each check you performed and add one line under it: what you did, what you saw, the screenshot path. Never tick a check you did not perform.
6. A failing check is a bug: fix it in the same phase, rerun the check, then commit.
7. Only a check needing something you cannot do (a real screen reader, a physical device) stays unchecked, marked `HUMAN-ONLY:` with the reason.

The parent refuses code review while any check is neither ticked nor `HUMAN-ONLY:`.

## Git

- Commit on your branch; one commit per phase. No AI attribution or `Co-Authored-By`.
- Do not push or open a PR until the parent says code review is done. The parent drives that step.
- Stay inside your ticket. Other sessions edit nearby files in parallel; keep the diff minimal so rebases stay easy.

## Talking to the parent

- SendMessage to the parent's session name (fallback `hc send <parent terminal>`), one line starting with your ticket id: when a step finishes, when you need a human decision (include the full paths of the artifact and its `.html`), or when blocked.
- When rpilayer ends a step with "Next: /clear, then /rpilayer", report and wait. The parent clears you.
- Start no agents except the subagents rpilayer itself uses.
