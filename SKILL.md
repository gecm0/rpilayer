---
name: rpilayer
description: Drive HumanLayer's Research-Plan-Implement workflow for a task (research questions, research, design, PRD/TDD, outline, implement, PR) locally, without the HumanLayer app. Use when the user says "rpilayer" or "rpi", starts a task from a ticket, asks to continue or advance a task, or gives feedback on a task artifact.
---

# rpilayer

The real workflow lives in the skills of HumanLayer's `rpi` plugin. That plugin is NOT installed: `/rpi:<x>` commands and `rpi:<name>` agents never exist as tools. rpilayer is the only entry point. It finds the task state, picks the step, and runs that step's instructions with local replacements for the HumanLayer app.

`DIR` below means the directory containing this file.

## 1. Read the state

```bash
python3 DIR/rpilayer.py state [SLUG]
```

Run this command from the repository or any of its worktrees, including subdirectories. It prints JSON: `task_dir`, `base` (the RPI plugin), `agents` (the RPI subagent definitions), `artifacts`, `latest`, `open_design_questions`, `checkboxes`, `next`, `iterate`, `steps` (the whole workflow with each step done, current, skipped or todo; the `mod/` folder draws it above the prompt).

`base` and `agents` point into a shallow checkout of github.com/humanlayer/humanlayer at `$HOME/.rpilayer/humanlayer`. `state` clones it on first use and pulls it at most once a day; offline it keeps the last copy. `RPI_REPO` overrides the checkout path.

Task documents live in `$HOME/.rpilayer/repos/<repo-id>/tasks/<slug>/`. The repo ID is stored in local Git config (`rpilayer.repo-id`), shared by all worktrees and retained when the checkout moves. Separate clones have separate IDs. State is derived from the documents, not stored as a separate snapshot.

- `migration_required`: stop the workflow and offer `python3 DIR/rpilayer.py migrate <slug>`. It imports legacy `.humanlayer/tasks/<slug>` documents from every registered worktree. Different content at the same relative path is a conflict: reconcile the listed files with the user and retry. A successful import archives the original task directories under each checkout's `.humanlayer/rpilayer-migrated/` and returns backup paths. Run migration without concurrent document edits, then rerun `state`. Omit the slug to migrate all legacy tasks.
- Without a slug, `state` picks the task this worktree last named (`state <slug>` in a linked worktree remembers it), then the task matching the branch, then the only task without `pr-description.md`.
- `error` with a `tasks` list: ask which task, or create a new one.
- Any other `error`: resolve it before selecting or running a step.
- New task: ask for the ticket if you do not have it. Choose a kebab-case slug, prefixed with the ticket id when there is one (`eng-1234-short-name`). Run `state <slug>` to obtain its absolute `task_dir`, create that directory, and write `ticket.md` there exactly as given, adding nothing: no repo facts, no decisions. Then pick the first step with `judge` (section 2).

Everything you need is in this file, the JSON, `<base>`, and `<agents>`. Do not read `rpilayer.py`, search for plugins, explore the repo, or read skills other than the chosen step before running it: the step does its own research.

## 2. Pick the step

- The user named a step (for example "create the plan"): run that step.
- The user wrote a message about the task: ask `judge` what it means. Pass the message and the recent conversation, verbatim and oldest first; your last turn matters most because the message usually answers it. The script adds the workflow state and the open sections of the current document, and trims to Jev's limits.

  ```bash
  python3 DIR/rpilayer.py judge <slug> <<'JSON'
  {"message": "<user message>", "conversation": [{"role": "user", "text": "..."}, {"role": "agent", "text": "..."}]}
  JSON
  ```

  - `intent` confidence below 0.7: ask the user one short question instead of guessing.
  - `advance` runs `next`. `iterate` runs `iterate`. `question`: answer it yourself, no step. `other`: leave the workflow.
  - No artifacts yet: `product_first` ≥ 0.6 runs `create-prd`, otherwise `create-research-questions`.
- Plain "/rpilayer" (or `/rpilayer:rpilayer`, `/skill:rpilayer`) or "continue": run `next`.
- If `next` is `done`, report that the local workflow is complete and stop. This means `pr-description.md` exists, not that the PR is merged. An explicitly requested step can still run.
- A HumanLayer text says "run `/rpi:<x>`": that is step `<x>`, run it through section 3.

Say the chosen step in one line, then run it.

## 3. Run the step

Read `<base>/skills/<step>/SKILL.md` fully and follow it, with these replacements:

- `{SKILLBASE}` is `<base>/skills/<step>`.
- "the task artifact directory from your system prompt", every `.humanlayer/tasks/...` artifact path, and `ENG-XXXX-description` all mean the absolute `task_dir` / `slug` returned by `state`. Use that directory for all document reads, writes, HTML views, and subagent handoffs, even after changing working directory. Workspace configuration files remain in the repository's `.humanlayer/`.
- "hook context says all design questions have been resolved" is true when `open_design_questions` is 0. Rerun `state` after editing the document.
- For `implement-outline` and `implement-plan`, use the autonomous phase loop below. It takes precedence over conflicting instructions in the upstream skill, implementer agents, checklists, and final templates, including approval gates and phase completion markers.
- Agents (`rpi:<name>`, or "the **<name>** agent"): read `<agents>/<name>.ts`. Its `prompt` template literal is the agent's instructions (unescape `\``, `\${` and `\\`). Spawn a general-purpose subagent with those instructions plus the task. If it sets `model`, pass it as the subagent's `model`. If it sets `tools`, tell the subagent to use only those tools. If the harness has no subagents, do the work inline.
- `mcp__humanlayer__*` tools, the library researcher, and artifact comments do not exist here. Do not mention them. Feedback arrives in chat and goes through the `iterate-*` step, so never run `review-artifact-comments`.
- Final answer templates (except autonomous implementation, which uses the report below): keep their content, but replace "button below", "sidebar", "cloud permalink", and "new session with `/rpi:<x>`" with the local artifact path, the HTML view path when one was built, and the "Next" line from section 5.

### Autonomous implementation

Run all remaining phases in order, starting with the first unchecked `- [ ] Phase N:` line in the outline or plan overview. If the overview lacks these lines, add them for the existing phases, preserving known completion status; `state` uses them to track implementation separately from manual checks.

For each phase:

1. **Implement.** Launch the step's implementer agent for this phase only. Pass the document paths and this autonomous workflow override; the agent returns its changes and verification results to you, not a request for human approval.
2. **Validate and fix.** Review the changes and run the phase's required checks, including any the implementer missed. Fix failures and rerun checks until they pass. Perform any manual checks you can actually execute; leave human-only checks unchecked and collect them for the final report. Never mark an unperformed check as passed.
3. **Commit and continue.** Create a commit containing only this phase's repository changes, preserving unrelated work and excluding task artifacts. After the commit succeeds, tick the phase's overview line and record its commit hash and validation results in the task document. Give a brief progress update and immediately start the next phase without asking for confirmation or a context reset.

Resolve implementation issues within the agreed plan autonomously. Pause only for a blocker you cannot safely resolve, such as missing access, a required product/design decision, or verification that cannot run and is necessary for safe continuation. Report the blocker and leave the phase incomplete; do not commit known-failing work or proceed past it.

After the final phase, report completed phases, commits, validation results, and outstanding human-only checks, then follow sections 4 and 5 once. This completes implementation, not the PR step; leave `describe-pr` as the next move.

## 4. Visual view

Build the HTML view only when it earns its cost. After creating or updating an artifact, build it if:

- the artifact has open questions the user must answer (for a design discussion, `open_design_questions` > 0 after rerunning `state`; for a PRD or TDD, an open-questions section with unresolved items). The view lets them pick options and copy the answers back;
- `<artifact>.html` already exists next to it, so the view the user asked for once never goes stale;
- or the user asks for it ("view", "HTML", "show me the HTML").

Otherwise skip it and say nothing about it.

To build it, spawn a general-purpose subagent using an inexpensive model available in the current harness (for example, Haiku or Luna) to build the HTML view, and wait for it. The view only restyles content that already exists, so an inexpensive model is sufficient. Give it only this task, with `DIR` and `<task_dir>` as absolute paths: "Read `DIR/view.md` and follow it to build the HTML view of `<task_dir>/<artifact>.md`. Read the artifact yourself; do not ask for more context." Do not write the HTML body yourself or pass it the artifact's text.

If the harness has no subagents, do it inline: read `DIR/view.md` again and follow it. Read it every time, even if you built a view earlier in this session: it changes, and HTML or scripts from earlier steps are never a valid template.

## 5. Close with the next move

Apply this section after the whole implementation loop, never between its phases. If implementation is blocked, ask only for what is needed to unblock it and stay in the current context.

A skill cannot clear its own context; only the user can. So end every completed step by telling them exactly what to type. Rerun `state` first and read `next`.

If `next` is `done`, report completion without a next-step command.

- **Moving to a new phase** (you finished a `create-*` or `implement-*` step, or `next` is a different phase than the one you just ran): the artifacts carry everything, and this conversation is now noise. End with the clear command for this harness, then the command that invoked this skill (`/rpilayer` as a skills-dir skill, `/rpilayer:rpilayer` as a Claude Code plugin, `/skill:rpilayer` in pi):

  ```
  Next: /clear, then /rpilayer        (Claude Code)
  Next: /new, then /rpilayer          (Codex, OpenCode)
  Next: /new, then /skill:rpilayer    (pi)
  ```

  Name only the line for the harness you are running in.
- **Staying in the phase** (you ran an `iterate-*` step, answered a question, or asked the user something): the conversation is the useful context. End with "Next: reply here" plus what you need from them, and do not suggest clearing.
