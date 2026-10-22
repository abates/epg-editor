import { services } from '$lib/server/services'
import { config } from '$lib/server/config'
import { fail } from '@sveltejs/kit'
import type { Actions, PageServerLoad } from './$types'

// FR-O-5: epg checkout, last sync, overlay sites and conflicts, index stats
export const load: PageServerLoad = async () => {
  return {
    sync: await services.syncStatus(),
    epg: { ...config.epg, dir: config.epgDir, overlayDir: config.overlayDir },
    epgOverride: await services.epgSourceOverride(),
    schedule: config.cronSchedule
  }
}

export const actions: Actions = {
  // Validates the repo/branch with `git ls-remote` and persists the override; the client
  // starts the actual sync via the existing "Sync now" job once this succeeds (issue #5)
  saveEpgSource: async ({ request }) => {
    const form = await request.formData()
    const repo = String(form.get('repo') ?? '').trim()
    const ref = String(form.get('ref') ?? '').trim()
    const values = { repo, ref }

    const errors: { repo?: string; ref?: string } = {}
    if (!repo) errors.repo = 'Required'
    if (!ref) errors.ref = 'Required'
    if (Object.keys(errors).length) return fail(400, { action: 'saveEpgSource', errors, values })

    const result = await services.saveEpgSource(repo, ref)
    if (!result.ok) return fail(422, { action: 'saveEpgSource', errors: result.errors, values })

    return { action: 'saveEpgSource', saved: true }
  },

  resetEpgSource: async () => {
    await services.resetEpgSource()

    return { action: 'resetEpgSource', saved: true }
  }
}
