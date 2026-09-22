# rpilayer

A Claude Code skill that runs [HumanLayer](https://github.com/humanlayer/humanlayer)'s Research-Plan-Implement (RPI) workflow locally, without the HumanLayer app.

## Credit

The workflow and the step instructions are HumanLayer's. rpilayer does not copy them: on first use it makes a sparse, shallow checkout of [github.com/humanlayer/humanlayer](https://github.com/humanlayer/humanlayer) in `~/.rpilayer/humanlayer`, then reads:

- the RPI skills from `apps/riptide-rpi-claude-plugin`
- the `rpi:*` subagent definitions from `apps/riptide-daemon/src/agents/claudecode/agents`

Both are Apache-2.0 licensed by HumanLayer. rpilayer is an independent project, not affiliated with or endorsed by HumanLayer.

## What rpilayer adds

The HumanLayer app normally supplies the task directory, design-question tracking, next-step suggestions, and cloud artifacts. rpilayer replaces them locally:

- `rpilayer.py state` derives the task state and the next step from the task documents in `~/.rpilayer/repos/<repo-id>/tasks/<slug>/`.
- `rpilayer.py judge` asks TypeSafe's Jev what a chat message means for the task (advance, iterate, question).
- `view.md` and `view-template.html` build HTML views of artifacts with open questions.
- `mod/` draws the workflow steps above the Claude Code prompt.

`SKILL.md` holds the instructions Claude follows.

## Install

Requires Claude Code, Python 3, and Git.

```bash
git clone https://github.com/gecm0/rpilayer.git ~/Developer/rpilayer
ln -s ~/Developer/rpilayer ~/.claude/skills/rpilayer
```

`judge` needs `TYPESAFE_API_KEY` in the environment.

For the progress band, add the mod directory to `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_PLUGIN_DIRS": "/path/to/rpilayer/mod" } }
```

Then type `/rpilayer` in Claude Code.

## Tests

```bash
python3 -m unittest
```

## License

[Apache License 2.0](LICENSE).
