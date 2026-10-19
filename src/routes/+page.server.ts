import { services } from '$lib/server/services'
import type { PageServerLoad } from './$types'

export const load: PageServerLoad = async () => {
  return { ...(await services.listLineups()), sync: await services.syncStatus() }
}
