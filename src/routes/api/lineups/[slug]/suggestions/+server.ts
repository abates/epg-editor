import { services } from '$lib/server/services'
import { error, json } from '@sveltejs/kit'
import type { RequestHandler } from './$types'

// Ranked guide entries for one channel of the lineup [FR-P-3]
export const GET: RequestHandler = async ({ params, url }) => {
  const key = url.searchParams.get('key')
  if (!key) error(400, 'Missing "key" parameter')

  const suggestions = await services.suggest(params.slug, key)

  return json({ key, suggestions })
}
