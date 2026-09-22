import { expect, mock, test } from 'claude-code/testing'

const STATE = {
  slug: 'eng-1-demo',
  steps: [
    { label: 'questions', status: 'done' },
    { label: 'research', status: 'done' },
    { label: 'design', status: 'skipped' },
    { label: 'outline', status: 'done' },
    { label: 'implement', status: 'current', detail: 'phase 3/5', doing: 'Phase 3: Add pagination' },
    { label: 'pr', status: 'todo' },
  ],
  next: 'implement-outline',
}

test('the band shows the task once rpilayer reads its state', async ($, on) => {
  on('tool.call', () => ({ result: { stdout: JSON.stringify(STATE), stderr: '', interrupted: false } }) as never)
  // Stands for the engine's own band: draws nothing.
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  for (const surface of ['terminal', 'desktop'] as const) {
    const before = await $.ui.mount({ plugin: 'rpilayer-band', surface, component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false } as never })
    expect(await before.find({ text: /rpi ·/ })).toBeUndefined()
    await before.unmount()
  }

  await $.tool.call({ tool: 'Bash', command: 'python3 /x/rpilayer.py state eng-1-demo' } as never)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'rpilayer-band', surface, component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false } as never })
    expect(await ui.find({ text: /eng-1-demo/ })).toBeDefined()
    expect(await ui.find({ text: /✓ research$/ })).toBeDefined()
    expect(await ui.find({ text: /– design/ })).toBeDefined()
    expect(await ui.find({ text: /◆ implement phase 3\/5/ })).toBeDefined()
    expect(await ui.find({ text: /○ pr/ })).toBeDefined()
    expect(await ui.find({ text: /now › implement · Phase 3: Add pagination/ })).toBeDefined()
    expect(await ui.find({ text: /then › pr/ })).toBeDefined()
    expect(await ui.find({ text: '3/5' })).toBeDefined()
    await ui.unmount()
  }
})

const BAND = { plugin: 'rpilayer-band', component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false } as never } as const

test('the band follows the task folder between the skill own state calls', async ($, on) => {
  const clock = mock.clock(on)
  let files = [{ name: '01-research-questions-a.md', kind: 'file', size: 10, mtimeMs: 1, isLink: false }]
  let script = { ...STATE, repo: '/repo', task_dir: '/tasks/eng-1-demo', next: 'create-research' }
  const runs: string[][] = []

  on('tool.call', () => ({ result: { stdout: JSON.stringify(script), stderr: '', interrupted: false } }) as never)
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })
  on('fs.list', () => ({ value: files }) as never)
  on('process.run', (_$, e) => {
    runs.push([...(e as { argv: string[] }).argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(script), stderr: '' } } as never
  })

  await $.tool.call({ tool: 'Bash', command: 'python3 /x/rpilayer.py state eng-1-demo' } as never)
  await clock.advance(2000)

  // A document written outside the skill: the band re-reads state for this task only.
  files = [...files, { name: '02-research-a.md', kind: 'file', size: 20, mtimeMs: 2, isLink: false }]
  script = { ...script, next: 'create-design-discussion', steps: [{ label: 'design', status: 'current' }, { label: 'outline', status: 'todo' }] }
  await clock.advance(2000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ text: /now › design/ })).toBeDefined()
  expect(await ui.find({ text: /then › outline/ })).toBeDefined()
  await ui.unmount()
  expect(runs.at(-1)?.slice(2)).toEqual(['state', 'eng-1-demo'])

  // Nothing changed: no new run.
  const count = runs.length
  await clock.advance(2000)
  expect(runs.length).toBe(count)

  // State from another task never replaces this session's.
  files = [...files, { name: 'x.md', kind: 'file', size: 1, mtimeMs: 3, isLink: false }]
  script = { ...script, slug: 'other-task', next: 'create-tdd', steps: [{ label: 'tdd', status: 'current' }] }
  await clock.advance(2000)
  const after = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await after.find({ text: /eng-1-demo/ })).toBeDefined()
  expect(await after.find({ text: /tdd/ })).toBeUndefined()
  await after.unmount()
})

test('a piped state call still moves the band to the task it names', async ($, on) => {
  const old = { ...STATE, slug: 'list-posts', repo: '/repo', task_dir: '/tasks/list-posts' }
  const fresh = { ...STATE, slug: 'new-task', repo: '/repo', task_dir: '/tasks/new-task', next: 'create-research' }
  const runs: string[][] = []
  let stdout = JSON.stringify(old)
  mock.clock(on)
  on('session.cwd', () => ({ value: '/repo' }) as never)

  on('tool.call', () => ({ result: { stdout, stderr: '', interrupted: false } }) as never)
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })
  on('process.run', (_$, e) => {
    runs.push([...(e as { argv: string[] }).argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(fresh), stderr: '' } } as never
  })

  await $.tool.call({ tool: 'Bash', command: 'python3 /x/rpilayer.py state' } as never)
  stdout = '/tasks/new-task None'
  await $.tool.call({ tool: 'Bash', command: 'python3 /x/rpilayer.py state new-task | python3 -c "..."' } as never)

  expect(runs.at(-1)?.slice(2)).toEqual(['state', 'new-task'])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ text: /new-task/ })).toBeDefined()
  expect(await ui.find({ text: /list-posts/ })).toBeUndefined()
  await ui.unmount()
})

test('a state call in a workspace with no task draws no band', async ($, on) => {
  const none = { repo: '/repo', tasks: [], error: 'pick a task slug (or create one)' }
  on('tool.call', () => ({ result: { stdout: JSON.stringify(none), stderr: '', interrupted: false } }) as never)
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  await $.tool.call({ tool: 'Bash', command: 'python3 /x/rpilayer.py state' } as never)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ text: /rpi/ })).toBeUndefined()
  await ui.unmount()
})
