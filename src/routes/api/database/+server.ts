import { services } from '$lib/server/services'
import { json } from '@sveltejs/kit'
import { limitParam } from '../params'
import type { RequestHandler } from './$types'

// xmltv_id search-as-you-type for the Manual tab [FR-E-1]
export const GET: RequestHandler = async ({ url }) => {
  const database = await services.database()
  const channels = database.find(url.searchParams.get('q') ?? '', limitParam(url, 20))

  return json({ channels })
}
