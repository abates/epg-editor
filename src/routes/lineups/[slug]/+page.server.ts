import { services } from '$lib/server/services'
import type { PageServerLoad } from './$types'

export const load: PageServerLoad = async ({ params }) => {
  const view = await services.viewLineup(params.slug)

  return {
    ...view,
    sites: await services.sites(),
    // Streamed: rows render at once, "Suggested" badges follow [FR-P-1, FR-P-3]
    suggestions: services.topSuggestions(params.slug).catch(() => null)
  }
}
