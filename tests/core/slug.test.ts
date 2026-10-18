import { isValidSlug, toSlug } from '$lib/core/slug'
import { describe, expect, it } from 'vitest'

describe('toSlug', () => {
  it.each([
    ['HDHomeRun – Living Room', 'hdhomerun-living-room'],
    ['Comcast (NYC) #2', 'comcast-nyc-2'],
    ['Télé Québec', 'tele-quebec'],
    ['___', '']
  ])('%j → %j', (name, slug) => {
    expect(toSlug(name)).toBe(slug)
  })
})

describe('isValidSlug', () => {
  it.each(['living-room', 'a', '0.1', 'ota.us'])('accepts %j', slug => {
    expect(isValidSlug(slug)).toBe(true)
  })

  it.each(['', '-a', '.hidden', '../etc', 'a/b', 'Upper', 'a b'])('rejects %j', slug => {
    expect(isValidSlug(slug)).toBe(false)
  })
})
