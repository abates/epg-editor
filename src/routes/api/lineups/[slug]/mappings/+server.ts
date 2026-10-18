import { parseMappingRequest } from '$lib/core/mappingValidation'
import { services } from '$lib/server/services'
import { error, json } from '@sveltejs/kit'
import type { RequestHandler } from './$types'

// Map or skip one channel [FR-P-4, FR-P-5, FR-P-6]. 422 with field errors for an invalid
// manual entry [FR-E-2]
export const PUT: RequestHandler = async ({ params, request }) => {
  const mapping = parseBody(await readJson(request))
  const result = await services.saveMapping(params.slug, mapping)
  if (!result.ok) return json({ errors: result.errors, warnings: result.warnings }, { status: 422 })

  return json({ row: result.row, warnings: result.warnings })
}

// Clear one channel's mapping [FR-P-5]
export const DELETE: RequestHandler = async ({ params, url }) => {
  const key = url.searchParams.get('key')
  if (!key) error(400, 'Missing "key" parameter')

  return json({ row: await services.clearMapping(params.slug, key), warnings: [] })
}

async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json()
  } catch {
    error(400, 'Expected a JSON body')
  }
}

function parseBody(body: unknown) {
  try {
    return parseMappingRequest(body)
  } catch (cause) {
    error(400, (cause as Error).message)
  }
}
