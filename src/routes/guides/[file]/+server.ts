import { guideETag, isNotModified, parseGuideFileName } from '$lib/core/guideFile'
import { GUIDES_DIR } from '$lib/server/grabRunner'
import { config } from '$lib/server/config'
import { error } from '@sveltejs/kit'
import { createReadStream } from 'node:fs'
import { Readable } from 'node:stream'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { RequestHandler } from './$types'

// FR-R-5: guides for Plex & co., 404 until the lineup's first successful grab
export const GET: RequestHandler = ({ params, request }) => serve(params.file, request, true)

export const HEAD: RequestHandler = ({ params, request }) => serve(params.file, request, false)

async function serve(file: string, request: Request, withBody: boolean): Promise<Response> {
  const name = parseGuideFileName(file)
  if (!name) error(404, 'Not found')

  const filepath = path.join(config.storageDir, GUIDES_DIR, file)
  const stat = await fs.stat(filepath).catch(() => null)
  if (!stat?.isFile()) error(404, `No guide for "${name.slug}" yet`)

  const stamp = { size: stat.size, mtime: stat.mtime }
  const headers = new Headers({
    'content-type': name.gzip ? 'application/gzip' : 'application/xml; charset=utf-8',
    'last-modified': stat.mtime.toUTCString(),
    etag: guideETag(stamp),
    'cache-control': 'no-cache'
  })
  if (isNotModified(request.headers, stamp)) return new Response(null, { status: 304, headers })

  headers.set('content-length', String(stat.size))
  if (!withBody) return new Response(null, { headers })

  // The file is replaced by rename, so an open stream keeps reading the version it opened
  const body = Readable.toWeb(createReadStream(filepath)) as ReadableStream<Uint8Array>

  return new Response(body, { headers })
}
