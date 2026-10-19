import { isValidSlug } from './slug'

export interface GuideFileName {
  slug: string
  gzip: boolean
}

export interface FileStamp {
  size: number
  mtime: Date
}

// `<slug>.xml` or `<slug>.xml.gz` with a valid slug, so a request can't leave /data/guides
// [FR-R-5, NFR-SEC-3]
export function parseGuideFileName(file: string): GuideFileName | null {
  const match = /^(.+)\.xml(\.gz)?$/.exec(file)
  if (!match || !isValidSlug(match[1])) return null

  return { slug: match[1], gzip: match[2] !== undefined }
}

export function guideETag({ size, mtime }: FileStamp): string {
  return `W/"${size.toString(16)}-${Math.floor(mtime.getTime()).toString(16)}"`
}

// RFC 9110 §13.1: If-None-Match wins over If-Modified-Since. HTTP dates have second precision
export function isNotModified(headers: Headers, stamp: FileStamp): boolean {
  const ifNoneMatch = headers.get('if-none-match')
  if (ifNoneMatch !== null) {
    const etag = guideETag(stamp)
    const tags = ifNoneMatch.split(',').map(tag => tag.trim().replace(/^W\//, ''))

    return tags.includes('*') || tags.includes(etag.replace(/^W\//, ''))
  }

  const ifModifiedSince = headers.get('if-modified-since')
  if (ifModifiedSince === null) return false
  const since = Date.parse(ifModifiedSince)
  if (Number.isNaN(since)) return false

  return Math.floor(stamp.mtime.getTime() / 1000) <= Math.floor(since / 1000)
}
