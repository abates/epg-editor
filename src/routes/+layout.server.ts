import { services } from '$lib/server/services'
import type { LayoutServerLoad } from './$types'

// The guide index is missing until the first sync has finished [NFR-DEP-3]
export const load: LayoutServerLoad = async () => {
  return {
    indexReady: (await services.guideIndex.get()) !== null,
    job: await services.jobs.status()
  }
}
