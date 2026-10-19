import { services } from '$lib/server/services'
import { config } from '$lib/server/config'
import type { PageServerLoad } from './$types'

// FR-O-5: epg checkout, last sync, overlay sites and conflicts, index stats
export const load: PageServerLoad = async () => {
  return {
    sync: await services.syncStatus(),
    epg: { ...config.epg, dir: config.epgDir, overlayDir: config.overlayDir },
    schedule: config.cronSchedule
  }
}
