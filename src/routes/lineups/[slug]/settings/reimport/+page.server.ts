import { parsePlaylist } from '$lib/core/playlistParser'
import { diffPlaylists } from '$lib/core/playlistDiff'
import { services } from '$lib/server/services'
import { error, redirect } from '@sveltejs/kit'
import type { Actions, PageServerLoad } from './$types'

// FR-M-6: review added / removed / renamed channels before the new playlist replaces the old
export const load: PageServerLoad = async ({ params }) => {
  const lineup = await services.lineups.get(params.slug)
  if (!lineup) error(404, `Lineup "${params.slug}" not found`)

  const pending = await services.lineups.loadPendingSource(params.slug)
  if (!pending) redirect(303, `/lineups/${params.slug}/settings`)

  const current = parsePlaylist(await services.lineups.loadSource(params.slug))
  const next = parsePlaylist(pending.m3u)
  const { items: mappings } = await services.lineups.loadMappings(params.slug)
  const diff = diffPlaylists(current.items, next.items)

  return {
    lineup,
    source: pending.source,
    diff,
    warnings: next.warnings,
    // Removed channels that are mapped or skipped, with that status
    removedMappings: Object.fromEntries(
      diff.removed.flatMap(channel => {
        const mapping = mappings[channel.key]
        return mapping ? [[channel.key, mapping.status]] : []
      })
    ) as Record<string, 'mapped' | 'skipped'>
  }
}

export const actions: Actions = {
  apply: async ({ params, request }) => {
    const form = await request.formData()
    const pending = await services.lineups.loadPendingSource(params.slug)
    if (!pending) redirect(303, `/lineups/${params.slug}/settings`)

    await services.lineups.reimport(params.slug, pending.m3u, pending.source, {
      dropRemoved: form.get('dropRemoved') === 'on'
    })
    redirect(303, `/lineups/${params.slug}`)
  },

  discard: async ({ params }) => {
    await services.lineups.discardPendingSource(params.slug)
    redirect(303, `/lineups/${params.slug}/settings`)
  }
}
