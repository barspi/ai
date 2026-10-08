// Which chat a Claude Code session belongs to.
//
// A CLI session id is not a chat: the Desktop app starts a new one when the
// app restarts or reconnects, and the chat goes on. The app keeps one record
// per chat (`claude-code-sessions/<account>/<org>/local_<uuid>.json`) that
// names the chat (`sessionId: "local_..."`), its current CLI session
// (`cliSessionId`) and the earlier ones (`priorCliSessionIds`).

/** The chat id in one app record when it lists `cliId`, else null. */
export const chatOfRecord = (cliId: string, raw: string): string | null => {
  try {
    const d = JSON.parse(raw) as {
      sessionId?: unknown
      cliSessionId?: unknown
      priorCliSessionIds?: unknown
    }
    const prior = Array.isArray(d.priorCliSessionIds) ? d.priorCliSessionIds : []
    const isMine = d.cliSessionId === cliId || prior.includes(cliId)

    return isMine && typeof d.sessionId === 'string' ? d.sessionId : null
  } catch {
    return null
  }
}

/** Where the Desktop app keeps its chat records, relative to the home folder. */
export const APP_SESSIONS = 'Library/Application Support/Claude/claude-code-sessions'
