import { GUIDES_DIR } from '$lib/server/grabRunner'
import { services } from '$lib/server/services'
import { config } from '$lib/server/config'
import { error } from '@sveltejs/kit'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { PageServerLoad } from './$types'

// FR-R-6: run history and the tail of one run's log (?log=<file>, default the newest)
export const load: PageServerLoad = async ({ params, url }) => {
  const lineup = await services.lineups.get(params.slug)
  if (!lineup) error(404, `Lineup "${params.slug}" not found`)

  const runs = await services.runs.list(params.slug).catch(() => [])
  const selected = url.searchParams.get('log') ?? runs.find(run => run.log)?.log ?? null
  const logLines = selected ? await services.runs.tail(params.slug, selected) : null
  if (url.searchParams.has('log') && !logLines) error(404, 'Log not found')

  return {
    lineup,
    runs,
    log: selected && logLines ? { name: selected, lines: logLines } : null,
    guides: {
      xml: await exists(`${params.slug}.xml`),
      gz: await exists(`${params.slug}.xml.gz`)
    }
  }
}

async function exists(file: string): Promise<boolean> {
  return fs.stat(path.join(config.storageDir, GUIDES_DIR, file)).then(
    stat => stat.isFile(),
    () => false
  )
}
