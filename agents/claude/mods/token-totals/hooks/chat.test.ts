import { expect, test } from 'claude-code/testing'

import { chatOfRecord } from './chat'

const record = (extra: Record<string, unknown>): string =>
  JSON.stringify({ sessionId: 'local_chat1', cliSessionId: 'cli-now', ...extra })

test('the current CLI session maps to the chat', () => {
  expect(chatOfRecord('cli-now', record({}))).toBe('local_chat1')
})

test('an earlier CLI session of the same chat maps to it too', () => {
  const raw = record({ priorCliSessionIds: ['cli-old', 'cli-older'] })

  expect(chatOfRecord('cli-old', raw)).toBe('local_chat1')
  expect(chatOfRecord('cli-older', raw)).toBe('local_chat1')
})

test('another chat, bad JSON and odd shapes give null', () => {
  expect(chatOfRecord('cli-other', record({ priorCliSessionIds: ['x'] }))).toBeNull()
  expect(chatOfRecord('cli-now', 'not json')).toBeNull()
  expect(chatOfRecord('cli-now', JSON.stringify({ cliSessionId: 'cli-now' }))).toBeNull()
  expect(chatOfRecord('cli-now', record({ priorCliSessionIds: 'nope' }))).toBe('local_chat1')
})
