import { describe, expect, it } from 'vitest'
import { formatDuration } from '$lib/core/formatDuration'

describe('formatDuration', () => {
  it('formats seconds, minutes and hours', () => {
    expect(formatDuration(950)).toBe('0s')
    expect(formatDuration(42_000)).toBe('42s')
    expect(formatDuration(75_000)).toBe('1m 15s')
    expect(formatDuration(3_725_000)).toBe('1h 2m 5s')
    expect(formatDuration(-5)).toBe('0s')
  })
})
