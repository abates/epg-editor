import { parseBulkMappingRequest } from '$lib/core/mappingValidation'
import { services } from '$lib/server/services'
import { error, json } from '@sveltejs/kit'
import type { RequestHandler } from './$types'

// Accept reviewed suggestions for several channels in one write [FR-P-7]
export const POST: RequestHandler = async ({ params, request }) => {
  const body = parseBody(await readJson(request))

  return json(await services.acceptEntries(params.slug, body))
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
    return parseBulkMappingRequest(body)
  } catch (cause) {
    error(400, (cause as Error).message)
  }
}
