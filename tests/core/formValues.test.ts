import { parseList, parseOptionalInteger } from '$lib/core/formValues'
import { describe, expect, it } from 'vitest'

describe('parseList', () => {
  it('splits on commas and whitespace, lower-cases and de-duplicates in order', () => {
    expect(parseList(' us, CA\nmx  us ')).toEqual(['us', 'ca', 'mx'])
    expect(parseList('')).toEqual([])
    expect(parseList(null)).toEqual([])
  })
})

describe('parseOptionalInteger', () => {
  it('treats blank as unset', () => {
    expect(parseOptionalInteger(' ')).toBeUndefined()
    expect(parseOptionalInteger(null)).toBeUndefined()
  })

  it('parses whole numbers within range', () => {
    expect(parseOptionalInteger(' 7 ', { min: 1, max: 14 })).toBe(7)
    expect(() => parseOptionalInteger('0', { min: 1, max: 14 })).toThrow('between 1 and 14')
    expect(() => parseOptionalInteger('1.5')).toThrow('whole number')
    expect(() => parseOptionalInteger('-1')).toThrow('whole number')
  })
})
