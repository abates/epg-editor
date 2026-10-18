import { parseList, parseOptionalInteger, toSentence } from '$lib/core/formValues'
import { readPlaylistInput } from '$lib/server/playlistInput'
import type { LineupGrabData } from '$lib/types/lineup'
import { services } from '$lib/server/services'
import { config } from '$lib/server/config'
import { error, fail, redirect } from '@sveltejs/kit'
import type { Actions, PageServerLoad } from './$types'

export const load: PageServerLoad = async ({ params }) => {
  const lineup = await services.lineups.get(params.slug)
  if (!lineup) error(404, `Lineup "${params.slug}" not found`)

  return { lineup, sites: await services.sites(), grabDefaults: config.grab }
}

const GRAB_LIMITS = {
  days: { label: 'Days', min: 1, max: 14 },
  maxConnections: { label: 'Max connections', min: 1, max: 100 },
  delay: { label: 'Delay', min: 0, max: 600_000 },
  timeout: { label: 'Timeout', min: 1, max: 600_000 }
}

const SAVE_FIELDS = [
  'name',
  'countries',
  'languages',
  'preferredSites',
  'enabled',
  'gzip',
  ...Object.keys(GRAB_LIMITS)
]

export const actions: Actions = {
  // FR-L-3 rename, FR-L-4 filters, FR-L-5 grab overrides
  save: async ({ params, request }) => {
    const form = await request.formData()
    // Sent back on failure so the form keeps what the user typed
    const values = Object.fromEntries(SAVE_FIELDS.map(name => [name, String(form.get(name) ?? '')]))

    const grab: Partial<LineupGrabData> = { enabled: form.get('enabled') === 'on' }
    for (const [field, limits] of Object.entries(GRAB_LIMITS)) {
      try {
        grab[field as keyof typeof GRAB_LIMITS] = parseOptionalInteger(form.get(field), limits)
      } catch (cause) {
        const error = `${limits.label} ${(cause as Error).message}`
        return fail(400, { action: 'save', error, values })
      }
    }
    const gzip = form.get('gzip')
    grab.gzip = gzip === 'on' ? true : gzip === 'off' ? false : undefined

    try {
      await services.lineups.update(params.slug, {
        name: String(form.get('name') ?? ''),
        filters: {
          countries: parseList(form.get('countries')),
          languages: parseList(form.get('languages')),
          preferredSites: parseList(form.get('preferredSites'))
        },
        grab
      })
    } catch (cause) {
      return fail(400, { action: 'save', error: toSentence((cause as Error).message), values })
    }

    return { action: 'save', saved: true }
  },

  // FR-M-6: the new playlist waits for review on the re-import page
  source: async ({ params, request }) => {
    const form = await request.formData()
    const lineup = await services.lineups.get(params.slug)
    if (!lineup) error(404, `Lineup "${params.slug}" not found`)

    // "Refresh from URL" re-fetches the stored URL
    if (form.get('refresh') === 'true') {
      form.set('sourceType', 'url')
      form.set('url', lineup.source.url ?? '')
    }

    const input = await readPlaylistInput(form)
    if (!input.ok) return fail(400, { action: 'source', error: input.error })

    await services.lineups.savePendingSource(params.slug, input.m3u, input.source)
    redirect(303, `/lineups/${params.slug}/settings/reimport`)
  },

  // FR-L-3
  delete: async ({ params }) => {
    await services.lineups.delete(params.slug)
    redirect(303, '/')
  }
}
