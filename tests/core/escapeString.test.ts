import { escapeString } from '$lib/core/escapeString'
import { describe, expect, it } from 'vitest'

// Expected values were produced by iptv-org/epg's own escapeString (scripts/core/utils.ts)
describe('escapeString', () => {
  it.each([
    ['A & B', 'A &amp; B'],
    [`<tag attr="x">'it'</tag>`, '&lt;tag attr=&quot;x&quot;&gt;&apos;it&apos;&lt;/tag&gt;'],
    ['line one\nline two\r\nline three', 'line one line two line three'],
    ['  lots    of   spaces  ', 'lots of spaces'],
    ['a\u0000b\u0008c\u000Bd\u001Fe', 'abcde'],
    ['a\tb', 'a\tb'],
    ['a\u007Fb\u0084c\u0085d\u009Fe', 'abc\u0085de'],
    ['a\uFFFEb\uFFFFc\uFDD0d', 'abcd'],
    ['a\uD800b', 'ab'],
    ['News 📺 HD', 'News 📺 HD'],
    ['&amp;', '&amp;amp;']
  ])('escapes %j', (input, expected) => {
    expect(escapeString(input)).toBe(expected)
  })

  it('returns the default value for empty input', () => {
    expect(escapeString('', 'n/a')).toBe('n/a')
    expect(escapeString(null)).toBe('')
    expect(escapeString(undefined)).toBe('')
  })
})
