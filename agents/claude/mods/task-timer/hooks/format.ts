/** `45s`, `3m 12s`, `1h 2m 5s`; `<1s` under half a second. */
export const formatDuration = (ms: number): string => {
  const total = Math.round(ms / 1000)
  if (!(total >= 1)) {
    return '<1s'
  }
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60

  return [h > 0 ? `${h}h` : '', h > 0 || m > 0 ? `${m}m` : '', `${s}s`]
    .filter(part => part !== '')
    .join(' ')
}
