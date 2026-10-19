import { services } from '$lib/server/services'
import { isValidSlug } from '$lib/core/slug'
import { error, json } from '@sveltejs/kit'
import type { RequestHandler } from './$types'

// Polled by the UI while a job runs
export const GET: RequestHandler = async () => {
  return json(await services.jobs.status())
}

// FR-R-3: { kind: 'sync' } or { kind: 'grab', lineup?: slug }; 409 while a run is in progress
export const POST: RequestHandler = async ({ request }) => {
  const body: unknown = await request.json().catch(() => null)
  if (typeof body !== 'object' || body === null) error(400, 'Expected a JSON body')

  const { kind, lineup } = body as { kind?: unknown; lineup?: unknown }
  if (kind !== 'sync' && kind !== 'grab') error(400, 'kind must be "sync" or "grab"')
  if (lineup !== undefined) {
    if (kind !== 'grab') error(400, 'lineup is only allowed for grab')
    if (typeof lineup !== 'string' || !isValidSlug(lineup)) error(400, 'Invalid lineup')
    if (!(await services.lineups.exists(lineup))) error(404, `Lineup "${lineup}" not found`)
  }

  const result = await services.jobs.start(kind, lineup as string | undefined)
  if (!result.ok) error(result.status, result.message)

  return json(await services.jobs.status(), { status: 202 })
}
