import { expect, mock, test } from 'claude-code/testing'

const USAGE = {
  model: 'm',
  input_tokens: 100,
  cache_creation_input_tokens: 50,
  cache_read_input_tokens: 2000,
  output_tokens: 30,
}

const turn = {
  answer: 'ok',
  durationMs: 1,
  isAborted: false,
  turnId: 't1',
  reason: 'answer' as const,
  usage: USAGE,
}

test('counts this chat only, under its own session id', async ($, on) => {
  mock.store(on, {
    'chat:abc': { input: 1000, cached: 0, output: 0 },
    'chat:other': { input: 999999, cached: 999999, output: 999999 },
  })
  mock.clock(on)
  mock.env(on, {}) // no HOME: the app's records are not looked for
  on('session.id', () => ({ value: 'abc' }) as never)
  const shown: Array<string | undefined> = []
  // The kit has no engine beneath the plugin, so the test answers these.
  on('ui.status', (_$, e) => {
    shown.push(e.text)

    return null as never
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('turn.complete', (_$, e) => ({ text: e.answer, usage: e.usage }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.complete(turn)
  await $.turn.complete(turn)

  expect(shown.at(0)).toBe('this chat: in 1.0k · cached 0 · out 0')
  expect(shown.at(-1)).toBe('this chat: in 1.3k · cached 4.0k · out 60')
})
