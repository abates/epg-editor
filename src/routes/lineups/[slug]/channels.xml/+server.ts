import { services } from '$lib/server/services'
import { error } from '@sveltejs/kit'
import type { RequestHandler } from './$types'

// FR-X-6: preview inline, or download with ?download
export const GET: RequestHandler = async ({ params, url }) => {
  if (!(await services.lineups.get(params.slug))) error(404, `Lineup "${params.slug}" not found`)

  const xml = await services.lineups.loadChannelsXml(params.slug)
  const headers: Record<string, string> = {
    'content-type': 'application/xml; charset=utf-8',
    'cache-control': 'no-store'
  }
  if (url.searchParams.has('download'))
    headers['content-disposition'] = `attachment; filename="${params.slug}.channels.xml"`

  return new Response(xml, { headers })
}
