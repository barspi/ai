import type { Register } from 'claude-code'

import { formatDuration } from './format'

const NOTE = {
  answer: '',
  aborted: ' (interrupted)',
  refusal: ' (refused)',
  error: ' (ended by an error)',
} as const

export const register: Register = on => {
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)

    // A subagent's turn ends inside the main one: only the main turn is a task.
    // The time is the wall clock from the prompt to the final answer, so it
    // includes any wait for your approval of a tool call.
    if (e.agentId === undefined) {
      const took = formatDuration(e.durationMs)
      $.ui.log(`⏱ Task took ${took}${NOTE[e.reason]}`)
      $.ui.status(`last task: ${took}`)
    }

    return done
  }).catch(($, e, next) => next(e))
}
