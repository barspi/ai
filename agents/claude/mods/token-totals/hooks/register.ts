import type { EngineInterface, Register } from 'claude-code'

import { APP_SESSIONS, chatOfRecord } from './chat'

type Totals = { input: number; cached: number; output: number }
type Found = { id: string; key: string }
type Cache = { current: Found | null }

const CHAT_PREFIX = 'chat:'
/** Newest app records read when looking for this chat's. */
const LOOKUP_LIMIT = 25

const EMPTY: Totals = { input: 0, cached: 0, output: 0 }

const compact = (n: number): string =>
  n >= 1e9
    ? `${(n / 1e9).toFixed(2)}B`
    : n >= 1e6
      ? `${(n / 1e6).toFixed(1)}M`
      : n >= 1e3
        ? `${(n / 1e3).toFixed(1)}k`
        : String(n)

const line = (t: Totals): string =>
  `this chat: in ${compact(t.input)} · cached ${compact(t.cached)} · out ${compact(t.output)}`

const num = (v: unknown): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : 0

const parse = (raw: unknown): Totals => {
  const r = (raw ?? {}) as Partial<Record<keyof Totals, unknown>>

  return { input: num(r.input), cached: num(r.cached), output: num(r.output) }
}

/**
 * The Desktop app's id for the chat this CLI session belongs to, or null (a
 * terminal session, or the app's record is not written yet).
 */
async function appChatOf($: EngineInterface, cliId: string): Promise<string | null> {
  try {
    const home = await $.env.get('HOME')
    if (!home) {
      return null
    }
    const base = `${home}/${APP_SESSIONS}`
    const files: Array<{ path: string; mtimeMs: number }> = []
    for (const account of await $.fs.list(base)) {
      for (const org of account.kind === 'dir' ? await $.fs.list(`${base}/${account.name}`) : []) {
        const dir = `${base}/${account.name}/${org.name}`
        for (const f of org.kind === 'dir' ? await $.fs.list(dir) : []) {
          if (f.kind === 'file' && f.name.startsWith('local_') && f.name.endsWith('.json')) {
            files.push({ path: `${dir}/${f.name}`, mtimeMs: f.mtimeMs })
          }
        }
      }
    }
    files.sort((a, b) => b.mtimeMs - a.mtimeMs)
    for (const f of files.slice(0, LOOKUP_LIMIT)) {
      const chat = chatOfRecord(cliId, String(await $.fs.read(f.path)))
      if (chat !== null) {
        return chat
      }
    }
  } catch {
    // no app records here: a terminal session
  }

  return null
}

/**
 * The store key of this chat's counter. The app's chat id when it is known
 * (it survives the app's restarts), else this session's own id. A count kept
 * under the session id before the chat id was known moves over to it.
 */
async function keyOf($: EngineInterface, cache: Cache): Promise<string> {
  const id = await $.session.id()
  if (cache.current?.id === id) {
    return cache.current.key
  }
  const own = CHAT_PREFIX + id
  const chat = await appChatOf($, id)
  if (chat === null) {
    return own // not cached: the app's record may show up on a later turn
  }
  const key = CHAT_PREFIX + chat
  const early = await $.store.get(own)
  if (early !== undefined) {
    const a = parse(await $.store.get(key))
    const b = parse(early)
    await $.store.set(key, {
      input: a.input + b.input,
      cached: a.cached + b.cached,
      output: a.output + b.output,
    })
    await $.store.delete(own)
  }
  cache.current = { id, key }

  return key
}

export const register: Register = (on) => {
  // One counter per chat in the plugin's store. Turns can end back to back
  // (subagents), so the read-modify-write goes through one queue.
  let queue: Promise<unknown> = Promise.resolve()
  const cache: Cache = { current: null }

  on('session.start', async ($, e, next) => {
    const key = await keyOf($, cache)
    $.ui.status(line(parse(await $.store.get(key))))

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const usage = e.usage

    if (usage) {
      queue = queue.then(async () => {
        const key = await keyOf($, cache)
        const t = parse((await $.store.get(key)) ?? EMPTY)
        // "input" counts every prompt token billed as new (fresh + written to
        // the cache); "cached" counts the ones the cache served.
        t.input += usage.input_tokens + usage.cache_creation_input_tokens
        t.cached += usage.cache_read_input_tokens
        t.output += usage.output_tokens
        await $.store.set(key, t)
        $.ui.status(line(t))
      })
      await queue
    }

    return next(e)
  }).catch(($, e, next) => next(e))
}
