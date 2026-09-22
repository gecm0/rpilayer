// The JSON printed by `rpilayer.py state`, only the fields the band reads.
export type Step = {
  label: string
  status: 'done' | 'current' | 'skipped' | 'todo'
  detail?: string
  // The phase line being implemented, on the current implement step.
  doing?: string
}

export type RpiState = {
  repo?: string
  task_dir?: string
  slug?: string
  error?: string
  steps?: Step[]
  next?: string
}

declare module 'claude-code' {
  interface PluginState {
    'rpilayer-band': { state: RpiState | null }
  }
}
