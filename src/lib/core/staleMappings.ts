import type { MappingGuideData, MappingsData } from '$lib/types/mapping'

export interface GuideLookup {
  hasEntry(site: string, site_id: string): boolean
  hasSite(site: string): boolean
}

// FR-G-4 / FR-P-8: after a sync, a mapping is stale when its guide entry is gone. Manual
// entries are never in a channels.xml, so they only go stale when their site disappears
export function markStaleMappings(
  mappings: MappingsData,
  lookup: GuideLookup
): { mappings: MappingsData; changed: number } {
  let changed = 0
  const items: MappingsData['items'] = {}

  for (const [key, mapping] of Object.entries(mappings.items)) {
    const stale =
      mapping.status === 'mapped' && !!mapping.guide && !isAvailable(mapping.guide, lookup)
    if (stale === !!mapping.stale) {
      items[key] = mapping
      continue
    }

    changed++
    const updated = { ...mapping }
    if (stale) updated.stale = true
    else delete updated.stale
    items[key] = updated
  }

  return { mappings: { ...mappings, items }, changed }
}

function isAvailable(guide: MappingGuideData, lookup: GuideLookup): boolean {
  if (guide.origin === 'manual') return lookup.hasSite(guide.site)

  return lookup.hasEntry(guide.site, guide.site_id)
}
