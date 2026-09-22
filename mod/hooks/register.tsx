import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { RpiState } from '../types'

const state = atom({ plugin: 'rpilayer-band', key: 'state' } as const, null)

// `judge` also reads state but prints Jev's answer, so only `state` counts.
const STATE_CALL = /rpilayer\.py\s+state\b/
const SLUG_CALL = /rpilayer\.py\s+state\s+([a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])/
const POLL_MS = 2000

// Vesper, the same palette as view-template.html.
const VESPER = {
  bright: '#ffffff',
  soft: '#bdbdbd',
  dim: '#8b8b8b',
  faint: '#4a4a4a',
  line: '#3a3a3a',
  peach: '#ffc799',
  mint: '#99ffe4',
} as const
const MARK = { done: '✓', current: '◆', skipped: '–', todo: '○' } as const
const LOOK = {
  done: { mark: VESPER.mint, label: VESPER.soft },
  current: { mark: VESPER.peach, label: VESPER.bright },
  skipped: { mark: VESPER.faint, label: VESPER.faint },
  todo: { mark: VESPER.faint, label: VESPER.dim },
} as const

// Each session keeps its own state, so terminals on different tasks never see each other's.
async function refresh($: EngineInterface, s: RpiState) {
  if (!s.repo || !s.slug) return
  // The mod lives in the rpilayer repo, next to the script.
  const script = `${$.plugin.root.replace(/\/$/, '')}/../rpilayer.py`
  const ran = await $.process.run(['python3', script, 'state', s.slug], { cwd: s.repo })
  const parsed = JSON.parse(ran.stdout) as RpiState
  // Another state call may have switched this session to a new task meanwhile.
  await update($, state, current => (current?.slug === parsed.slug ? parsed : current))
}

// Module state: a reload starts these over, and session.start picks the watch back up.
let timer: Timer | undefined
let stamp = ''
let isBusy = false

// Documents change outside the skill's own state calls (an agent mid-step, an editor), so
// the band watches the task folder of this session and re-reads the state when it moves.
function watch($: EngineInterface) {
  timer ??= $.clock.every(POLL_MS, async () => {
    const s = await read($, state)
    if (isBusy || !s?.task_dir) return
    isBusy = true
    try {
      const entries = await $.fs.list(s.task_dir)
      const next = entries.map(f => `${f.name}:${f.mtimeMs}:${f.size}`).sort().join('|')
      if (next !== stamp) {
        stamp = next
        await refresh($, s)
      }
    } catch {
      // Folder not written yet or script output unreadable: try again next tick.
    } finally {
      isBusy = false
    }
  })
}

export const register: Register = on => {
  // A reload starts the module over while $.state keeps the task: pick the watch back up.
  on('session.start', async ($, e, next) => {
    if (await read($, state)) watch($)
    return next(e)
  })

  // The skill runs `state` at the start and end of every step: take its output as is.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (!STATE_CALL.test(e.command) || ran.deny !== undefined || ran.isError) return ran

    const stdout = (ran.result as { stdout?: unknown } | undefined)?.stdout
    try {
      const parsed = JSON.parse(typeof stdout === 'string' ? stdout : '') as RpiState
      await update($, state, () => parsed)
      watch($)
    } catch {
      // Output piped through a filter: the named task still becomes this session's,
      // otherwise the band would stay on the task it showed before.
      const slug = e.command.match(SLUG_CALL)?.[1]
      if (slug) {
        await update($, state, () => ({ slug }))
        // Swallowed: a throw here would reach .catch below, which runs the Bash call again.
        const repo = await $.session.cwd().catch(() => undefined)
        await refresh($, { repo, slug }).catch(() => {})
        watch($)
      }
    }
    return ran
  }).catch(($, e, next) => next(e)) // a failure here must never block the Bash call

  // The step list comes whole from rpilayer.py, so the band knows nothing about the workflow.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, state)
    // No task picked (a bare `state` in a workspace with none): nothing to show.
    if (e.props.hasSurvey || !s?.slug) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    if (s.error || !s.steps) {
      return (
        <Box borderStyle="round" borderColor={VESPER.line} paddingX={1}>
          <Text color={VESPER.peach} bold>rpi </Text>
          <Text color={VESPER.dim}>{s.error ?? s.slug}</Text>
        </Box>
      )
    }

    const counted = s.steps.filter(step => step.status !== 'skipped')
    const done = counted.filter(step => step.status === 'done').length
    // `next` is the step the skill runs now, so the band says "now" and names what follows.
    const at = s.steps.findIndex(step => step.status === 'current')
    const current = s.steps[at]
    const then = at < 0 ? undefined : s.steps.slice(at + 1).find(step => step.status === 'todo')

    return (
      <Box flexDirection="column" borderStyle="round" borderColor={VESPER.line} paddingX={1}>
        <Box justifyContent="space-between">
          <Text>
            <Text color={VESPER.peach} bold>rpi</Text>
            <Text color={VESPER.faint}> · </Text>
            <Text color={VESPER.bright}>{s.slug}</Text>
          </Text>
          <Text color={VESPER.dim}>{done}/{counted.length}</Text>
        </Box>
        <Box flexWrap="wrap">
          {s.steps.map((step, i) => (
            <Text key={step.label}>
              {i > 0 ? <Text color={VESPER.faint}> ── </Text> : null}
              <Text color={LOOK[step.status].mark} bold={step.status === 'current'}>{MARK[step.status]} </Text>
              <Text color={LOOK[step.status].label} bold={step.status === 'current'} strikethrough={step.status === 'skipped'}>
                {step.label}
              </Text>
              {step.detail ? <Text color={VESPER.peach} italic> {step.detail}</Text> : null}
            </Text>
          ))}
        </Box>
        {current ? (
          <Box justifyContent="space-between">
            <Text>
              <Text color={VESPER.dim}>now </Text>
              <Text color={VESPER.peach}>› </Text>
              <Text color={VESPER.bright}>{current.label}</Text>
              {current.doing ? <Text color={VESPER.soft}> · {current.doing}</Text> : null}
            </Text>
            {then ? (
              <Text>
                <Text color={VESPER.dim}>then </Text>
                <Text color={VESPER.faint}>› </Text>
                <Text color={VESPER.dim}>{then.label}</Text>
              </Text>
            ) : null}
          </Box>
        ) : (
          <Text>
            <Text color={VESPER.dim}>next </Text>
            <Text color={VESPER.peach}>› </Text>
            <Text color={VESPER.soft}>{s.next}</Text>
          </Text>
        )}
      </Box>
    )
  })
}
