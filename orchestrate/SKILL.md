---
name: orchestrate
description: Run several tickets in parallel as child Claude sessions, one graft worktree each, driven by this parent session through rpilayer, browser verification, code review and PR. Use when the user says "orchestrate", "lanza estos tickets", "lote", asks to run tickets in parallel worktrees, or asks to resume an orchestrated batch.
---

# Orchestrate

`DIR` is this file's folder. You are the parent. Children do the work; you launch them, move them through gates, and tell the user only what needs them.

## 0. Preconditions (check every time, stop on the first failure)

1. `hc`, `graft`, `herdr-app` and `agent-browser` are on PATH, and `ocr --version` works.
2. The repo has `graft.toml` with an `[agent]` command and a setup hook. Without `[agent]`, `graft create --open herdr` opens no agent tab.
3. The repo's `AGENTS.md` has a **worktree contract**: how setup gives each worktree its own environment, how to check it, how to restart it, how to start the UI, how to log in, what is forbidden. Missing → stop and write it with the user before launching anything. Never invent it: a child with no contract falls back to shared environments.
4. `rpilayer.py` exists in the parent folder of this skill (the rpilayer repo root).
5. Your own session name: run `ListAgents`; the first line names this session. Children report to that name.

State for a batch lives in `~/.local/state/orchestrate/<repo>/<batch>/` (ticket list, terminal map, reports). Never in `/tmp`: it is wiped on reboot.

## 1. Choose the batch

- 3 to 5 tickets. Map the files and functions each one touches (delegate the mapping to a subagent; it reads, you keep the conclusion).
- Same function in two tickets → never in the same batch. Same file, different functions → allowed; the second to merge rebases.
- Run the batch past Codex before proposing it, then ask the user. The user picks the scope; never launch an unapproved ticket.

## 2. Launch one child (repeat per ticket)

1. Get the ticket (Linear MCP): title, description, `gitBranchName`. Slug = the branch name without its user prefix.
2. From the main checkout: `python3 <rpilayer repo>/rpilayer.py state <slug>`, create its `task_dir`, write `ticket.md` with the ticket text exactly as given. Do this before `graft create`: with `--open herdr` the child starts as soon as setup ends, and without `ticket.md` rpilayer stops to ask for the ticket.
3. `graft create --branch <graft user>/<slug> --setup inline --open herdr --task "<task>"`. The task names the ticket, the parent session, the repo's worktree contract section, and says: "Read DIR/child-brief.md and follow it exactly." Never use `graft create --linear`: graft's Linear key may belong to another workspace.
4. Find the child's terminal: `hc ls --json`, `cwd` equal to the worktree, agent `claude-code`. Herdr starts it, so it is not your hc child and `hc wait --children` cannot see it.
5. Subscribe: `SendMessage` to the child's session name with `notify_when_idle: true`. Record ticket, slug, worktree, terminal and session name in the batch state.
6. Mark the ticket In Progress.

## 3. React to each event

Never wait in the foreground. Children wake you with SendMessage or an idle notice; `DIR/scripts/monitor.sh <worktrees-dir>` in the background is the fallback. While blocked in a foreground wait you cannot react, and children stall.

On every report or idle notice, read the state (`python3 <rpilayer repo>/rpilayer.py state` run from the child's worktree), not the screen, then walk this tree:

```
open_design_questions > 0, or the child asks for a decision?
├── Yes → tell the user NOW: ticket, full artifact path, full .html path.
│         Run any Codex review in parallel, never before the message.
│         Relay the answers to the child, or let the user answer in its tab.
└── No
    ├── next is a research/design/outline/plan step
    │   └── DIR/scripts/advance.sh <terminal> <worktree>
    ├── implementation reported done
    │   ├── DIR/scripts/verify-gate.sh <worktree> fails → send the child back to verify in the browser
    │   └── passes → advance.sh <terminal> <worktree> "Run /open-code-review:review with the arguments --from origin/main --to HEAD. Fix what is worth adopting, rerun checks, commit. Do not push yet. Report adopted and rejected findings."
    ├── OCR reported → read the findings yourself; then
    │   advance.sh <terminal> <worktree> "/rpilayer (code review is done, push and PR are approved; report the PR URL and the CI result)"
    ├── PR open with CI green → tell the user: PR URL, what to review closely, merge-order conflicts with other PRs
    └── blocked / ABORT / dead terminal → read the child's screen (hc read), fix the cause or ask the user
```

Why `advance.sh`: `/clear` only works as typed keys (`hc keys <t> / c l e a r enter`); `hc send "/clear"` arrives wrapped as a message and the model just replies. Skill commands work through `hc send` because the model invokes them.

## 4. After merges

- Pull main in the main checkout.
- Remove a worktree only after checking: PR merged, `git status` clean, no commits missing from the remote. Then `graft remove <worktree>` (its teardown stops the worktree's servers) and delete the local branch; squash merges leave it looking unmerged.
- Merged without browser verification → run one verification session on main (a child with a verify-only task, no code changes), then fix findings in one new worktree with the same gates.

## 5. Rules

- **Production is forbidden.** Never deploy, tag a release, use deploy keys or `--prod`, and never let a child do it.
- **Shared environments are off limits for children.** Each worktree uses only its own environment from the contract.
- **Before any write to a shared system, prove the target first with a read.** graft is a Bun binary and Bun loads the `.env*` of the folder it runs from, so hooks and agents can inherit the main checkout's environment selectors, and many CLIs let env vars win over files. In one repo this wrote to a shared dev deployment.
- **`set -o pipefail` scripts:** `lsof`, `find`, `ls` and `grep` with no results exit non-zero and abort silently. Wrap them in `( ... || true)`. macOS has no `timeout`.
- **Commits, push and PR:** children commit freely; push and PR only after code review. No AI attribution anywhere. The same order applies to PRs you open yourself.
- **OCR skips Markdown** ("no items were selected"). For a docs-only change, check every claim against the code or a command you ran, and say so in the report.
- **Talk to the user in prose**: one decision per question, full paths, no tool dialogs. Evidence goes in the batch state or the PR, not in the question.
