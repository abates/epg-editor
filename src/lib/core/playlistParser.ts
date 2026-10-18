import { parseM3U, type M3uChannel } from '@iptv/playlist'
import type { PlaylistItemData, PlaylistParseResult } from '$lib/types/playlist'

// @iptv/playlist moves these attributes into camelCase fields; everything else lands in `extras`
const KNOWN_ATTRIBUTES: [keyof M3uChannel, string][] = [
  ['tvgId', 'tvg-id'],
  ['tvgName', 'tvg-name'],
  ['tvgLanguage', 'tvg-language'],
  ['tvgLogo', 'tvg-logo'],
  ['tvgUrl', 'tvg-url'],
  ['tvgRec', 'tvg-rec'],
  ['tvgChno', 'tvg-chno'],
  ['groupTitle', 'group-title'],
  ['timeshift', 'timeshift'],
  ['catchup', 'catchup'],
  ['catchupDays', 'catchup-days'],
  ['catchupSource', 'catchup-source']
]

const KEY_ATTRIBUTES = ['channel-number', 'tvg-chno', 'channel-id', 'tvg-id']
const NUMBER_ATTRIBUTES = ['channel-number', 'tvg-chno']
const LEADING_NUMBER = /^(\d+(?:\.\d+)?)(?:\s+|$)/
const HTTP_URL = /^https?:\/\//i
const ATTRIBUTES = '(?:\\s+[A-Za-z][\\w-]*="[^"]*")*'
const EXTM3U_LINE = new RegExp(`^#EXTM3U${ATTRIBUTES}\\s*$`)
const EXTINF_LINE = new RegExp(`^#EXTINF:\\s*-?\\d+(?:\\.\\d+)?${ATTRIBUTES}\\s*,(.*)$`)

export function parsePlaylist(content: string): PlaylistParseResult {
  const { text, entries, warnings } = sanitize(content)

  const channels = parseM3U(text).channels
  const skipped = entries - channels.length
  if (skipped > 0) {
    warnings.push(`${skipped} of ${entries} entries could not be parsed and were skipped`)
  }

  const keys = new Map<string, number>()
  const items: PlaylistItemData[] = channels.map(channel => {
    const attributes = getAttributes(channel)
    const title = (channel.name ?? '').trim()
    const number = getNumber(attributes, title)
    const name = getName(attributes, title, number)
    const url = (channel.url ?? '').trim()

    let key = getKey(attributes, url, title)
    const count = (keys.get(key) ?? 0) + 1
    keys.set(key, count)
    if (count > 1) {
      warnings.push(`duplicate key "${key}" for "${title}", renamed to "${key}#${count}"`)
      key = `${key}#${count}`
    }

    return {
      key,
      number,
      name,
      url,
      logo: attributes['tvg-logo'] || null,
      group: attributes['group-title'] || null,
      attributes
    }
  })

  return { items, warnings }
}

// @iptv/playlist loops forever when it reaches an `=` with no `"` anywhere after it, and it
// drops non-http stream URLs. Only lines that match a strict grammar are passed through, and a
// trailing `#"` comment guarantees a closing quote always exists.
// See docs/upstream/iptv-playlist-infinite-loop.md
function sanitize(content: string): { text: string; entries: number; warnings: string[] } {
  const lines = content.replace(/^\uFEFF/, '').split(/\r?\n/)
  const output: string[] = []
  const warnings: string[] = []
  let entries = 0
  let pending: { line: number; title: string } | null = null
  let skipping = false

  for (const [index, raw] of lines.entries()) {
    const line = raw.trim()
    const lineNumber = index + 1

    if (!line) continue
    if (line.startsWith('#EXTM3U')) {
      if (EXTM3U_LINE.test(line)) output.push(line)
      else {
        warnings.push(`line ${lineNumber}: malformed #EXTM3U attributes ignored`)
        output.push('#EXTM3U')
      }
      continue
    }
    if (line.startsWith('#EXTINF:')) {
      if (pending) warnings.push(`line ${pending.line}: "${pending.title}" has no stream URL`)
      const match = line.match(EXTINF_LINE)
      pending = match ? { line: lineNumber, title: match[1].trim() } : null
      skipping = !match
      if (match) output.push(line)
      else warnings.push(`line ${lineNumber}: malformed #EXTINF attributes, entry skipped`)
      continue
    }
    if (line.startsWith('#')) {
      if (!skipping) output.push(line)
      continue
    }
    if (skipping) {
      skipping = false
      continue
    }
    if (!HTTP_URL.test(line)) {
      if (pending) {
        warnings.push(
          `line ${lineNumber}: "${pending.title}" skipped, only http(s) URLs are supported`
        )
        pending = null
      } else {
        warnings.push(`line ${lineNumber}: unrecognised line skipped`)
      }
      continue
    }
    if (!pending) {
      warnings.push(`line ${lineNumber}: stream URL without #EXTINF skipped`)
      continue
    }

    entries++
    pending = null
    output.push(line)
  }

  if (pending) warnings.push(`line ${pending.line}: "${pending.title}" has no stream URL`)
  output.push('#"')

  return { text: output.join('\n') + '\n', entries, warnings }
}

function getAttributes(channel: M3uChannel): Record<string, string> {
  const attributes: Record<string, string> = {}
  for (const [field, name] of KNOWN_ATTRIBUTES) {
    const value = channel[field]
    if (typeof value === 'string') attributes[name] = value
  }
  for (const [name, value] of Object.entries(channel.extras ?? {})) {
    if (typeof value === 'string') attributes[name] = value
  }

  return attributes
}

function firstAttribute(attributes: Record<string, string>, names: string[]): string | null {
  for (const name of names) {
    const value = attributes[name]?.trim()
    if (value) return value
  }

  return null
}

function getNumber(attributes: Record<string, string>, title: string): string | null {
  return firstAttribute(attributes, NUMBER_ATTRIBUTES) ?? title.match(LEADING_NUMBER)?.[1] ?? null
}

// HDHomeRun titles look like "2.1 WCBS-HD"; the guide display name should be "WCBS-HD"
function getName(attributes: Record<string, string>, title: string, number: string | null) {
  const tvgName = attributes['tvg-name']?.trim()
  if (tvgName) return tvgName

  const match = title.match(LEADING_NUMBER)
  if (match && match[1] === number && title.length > match[0].length) {
    return title.slice(match[0].length).trim()
  }

  return title
}

function getKey(attributes: Record<string, string>, url: string, title: string): string {
  return (
    firstAttribute(attributes, KEY_ATTRIBUTES) ?? (url || title.toLowerCase().replace(/\s+/g, ' '))
  )
}
