import { services } from '$lib/server/services'
import { json } from '@sveltejs/kit'
import { limitParam } from '../params'
import type { RequestHandler } from './$types'

// Guide entry search for the mapping modal's Search tab [FR-P-4]
export const GET: RequestHandler = async ({ url }) => {
  const matcher = await services.matcher()
  const entries = matcher.find(url.searchParams.get('q') ?? '', {
    site: url.searchParams.get('site') || undefined,
    country: url.searchParams.get('country') || undefined,
    lang: url.searchParams.get('lang') || undefined,
    limit: limitParam(url, 50)
  })

  return json({ entries })
}
