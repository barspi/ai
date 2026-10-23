import { expect, test } from 'claude-code/testing'

import { formatDuration } from './format'

const turn = (extra: Record<string, unknown>) => ({
  answer: 'done',
  durationMs: 192_000,
  isAborted: false,
  turnId: 't1',
  reason: 'answer' as const,
  ...extra,
})

test('durations read as seconds, minutes and hours', () => {
  expect(formatDuration(0)).toBe('<1s')
  expect(formatDuration(400)).toBe('<1s')
  expect(formatDuration(45_000)).toBe('45s')
  expect(formatDuration(60_000)).toBe('1m 0s')
  expect(formatDuration(192_000)).toBe('3m 12s')
  expect(formatDuration(3_725_000)).toBe('1h 2m 5s')
  expect(formatDuration(Number.NaN)).toBe('<1s')
})

test('a finished task logs its total time and keeps it in the status line', async ($, on) => {
  const logs: string[] = []
  const status: Array<string | undefined> = []
  on('ui.log', (_$, e) => {
    logs.push(e.text)

    return { value: undefined } as never
  })
  on('ui.status', (_$, e) => {
    status.push(e.text)

    return { value: undefined } as never
  })
  on('turn.complete', (_$, e) => ({ text: e.answer }))

  await $.turn.complete(turn({}))
  await $.turn.complete(turn({ durationMs: 2_000, reason: 'aborted', isAborted: true }))

  expect(logs).toEqual(['⏱ Task took 3m 12s', '⏱ Task took 2s (interrupted)'])
  expect(status.at(-1)).toBe('last task: 2s')
})

test('a subagent turn is not a task', async ($, on) => {
  const logs: string[] = []
  on('ui.log', (_$, e) => {
    logs.push(e.text)

    return { value: undefined } as never
  })
  on('ui.status', () => ({ value: undefined }) as never)
  on('turn.complete', (_$, e) => ({ text: e.answer }))

  await $.turn.complete(turn({ agentId: 'sub-1' }))

  expect(logs).toEqual([])
})
