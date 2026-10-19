import { describe, expect, it } from 'vitest'
import { guideETag, isNotModified, parseGuideFileName } from '$lib/core/guideFile'

const stamp = { size: 1234, mtime: new Date('2026-01-01T10:00:00.500Z') }

describe('parseGuideFileName', () => {
  it('accepts <slug>.xml and <slug>.xml.gz', () => {
    expect(parseGuideFileName('ota.xml')).toEqual({ slug: 'ota', gzip: false })
    expect(parseGuideFileName('ota.xml.gz')).toEqual({ slug: 'ota', gzip: true })
    expect(parseGuideFileName('living-room.v2.xml')).toEqual({
      slug: 'living-room.v2',
      gzip: false
    })
  })

  it('rejects other names and path tricks [NFR-SEC-3]', () => {
    for (const file of [
      'ota',
      'ota.json',
      '.tmp-ota.xml',
      '..xml',
      '../ota.xml',
      'OTA.xml',
      '.xml'
    ])
      expect(parseGuideFileName(file), file).toBeNull()
  })
})

describe('isNotModified', () => {
  const headers = (init: Record<string, string>) => new Headers(init)

  it('matches If-None-Match against the ETag, weak or strong', () => {
    const etag = guideETag(stamp)

    expect(isNotModified(headers({ 'if-none-match': etag }), stamp)).toBe(true)
    expect(isNotModified(headers({ 'if-none-match': etag.slice(2) }), stamp)).toBe(true)
    expect(isNotModified(headers({ 'if-none-match': `"x", ${etag}` }), stamp)).toBe(true)
    expect(isNotModified(headers({ 'if-none-match': '*' }), stamp)).toBe(true)
    expect(isNotModified(headers({ 'if-none-match': '"x"' }), stamp)).toBe(false)
  })

  it('changes the ETag when size or mtime change', () => {
    expect(guideETag({ ...stamp, size: 1 })).not.toBe(guideETag(stamp))
    expect(guideETag({ ...stamp, mtime: new Date('2026-01-02') })).not.toBe(guideETag(stamp))
  })

  it('compares If-Modified-Since to the second', () => {
    const lastModified = stamp.mtime.toUTCString()

    expect(isNotModified(headers({ 'if-modified-since': lastModified }), stamp)).toBe(true)
    expect(
      isNotModified(headers({ 'if-modified-since': 'Thu, 01 Jan 2026 09:59:59 GMT' }), stamp)
    ).toBe(false)
    expect(isNotModified(headers({ 'if-modified-since': 'garbage' }), stamp)).toBe(false)
  })

  it('ignores If-Modified-Since when If-None-Match is present', () => {
    const lastModified = stamp.mtime.toUTCString()

    expect(
      isNotModified(headers({ 'if-none-match': '"x"', 'if-modified-since': lastModified }), stamp)
    ).toBe(false)
  })

  it('is false without conditional headers', () => {
    expect(isNotModified(headers({}), stamp)).toBe(false)
  })
})
