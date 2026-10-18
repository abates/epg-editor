import { readPlaylistInput } from '$lib/server/playlistInput'
import { services } from '$lib/server/services'
import { parseList, toSentence } from '$lib/core/formValues'
import { fail, redirect } from '@sveltejs/kit'
import type { Actions, PageServerLoad } from './$types'

export const load: PageServerLoad = async () => {
  return { sites: await services.sites() }
}

export const actions: Actions = {
  // FR-L-1, FR-M-1, FR-M-2, FR-L-4
  default: async ({ request }) => {
    const form = await request.formData()
    const values = {
      name: String(form.get('name') ?? ''),
      slug: String(form.get('slug') ?? ''),
      sourceType: String(form.get('sourceType') ?? 'upload'),
      url: String(form.get('url') ?? ''),
      countries: String(form.get('countries') ?? ''),
      preferredSites: String(form.get('preferredSites') ?? '')
    }

    if (!values.name.trim()) return fail(400, { values, error: 'Enter a name for the lineup' })

    const input = await readPlaylistInput(form)
    if (!input.ok) return fail(400, { values, error: input.error })

    let slug: string
    try {
      const lineup = await services.lineups.create({
        name: values.name,
        slug: values.slug.trim() || undefined,
        source: input.source,
        m3u: input.m3u,
        filters: {
          countries: parseList(values.countries),
          preferredSites: parseList(values.preferredSites)
        }
      })
      slug = lineup.slug
    } catch (error) {
      return fail(400, { values, error: toSentence((error as Error).message) })
    }

    redirect(303, `/lineups/${slug}`)
  }
}
