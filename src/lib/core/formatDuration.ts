// 950 → "0s", 75_000 → "1m 15s", 3_725_000 → "1h 2m 5s"
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60

  if (hours) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes) return `${minutes}m ${seconds}s`

  return `${seconds}s`
}
