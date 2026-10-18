import { markStaleMappings, type GuideLookup } from '$lib/core/staleMappings'
import type { MappingData, MappingsData } from '$lib/types/mapping'
import { describe, expect, it } from 'vitest'

const lookup: GuideLookup = {
  hasEntry: (site, site_id) => site === 'tvtv.us' && site_id === '10098',
  hasSite: site => site === 'tvtv.us'
}

function mapped(site: string, site_id: string, extra: Partial<MappingData> = {}): MappingData {
  return {
    status: 'mapped',
    guide: { site, site_id, lang: 'en', xmltv_id: '', name: site_id, origin: 'upstream' },
    updatedAt: '2026-10-18T00:00:00.000Z',
    ...extra
  }
}

function mappings(items: Record<string, MappingData>): MappingsData {
  return { version: 1, items }
}

describe('markStaleMappings', () => {
  it('marks mappings whose entry is gone', () => {
    const result = markStaleMappings(
      mappings({ a: mapped('tvtv.us', '10098'), b: mapped('tvtv.us', 'gone') }),
      lookup
    )

    expect(result.changed).toBe(1)
    expect(result.mappings.items.a.stale).toBeUndefined()
    expect(result.mappings.items.b.stale).toBe(true)
  })

  it('clears the flag when the entry is back', () => {
    const result = markStaleMappings(
      mappings({ a: mapped('tvtv.us', '10098', { stale: true }) }),
      lookup
    )

    expect(result.changed).toBe(1)
    expect('stale' in result.mappings.items.a).toBe(false)
  })

  it('checks manual mappings by site only', () => {
    const manual = (site: string) => {
      const mapping = mapped(site, 'custom-id')
      mapping.guide!.origin = 'manual'
      return mapping
    }
    const result = markStaleMappings(
      mappings({ a: manual('tvtv.us'), b: manual('gone.example') }),
      lookup
    )

    expect(result.mappings.items.a.stale).toBeUndefined()
    expect(result.mappings.items.b.stale).toBe(true)
  })

  it('ignores skipped channels and keeps unchanged mappings as they are', () => {
    const skipped: MappingData = { status: 'skipped', updatedAt: '2026-10-18T00:00:00.000Z' }
    const fresh = mapped('tvtv.us', '10098')
    const result = markStaleMappings(mappings({ a: skipped, b: fresh }), lookup)

    expect(result.changed).toBe(0)
    expect(result.mappings.items.a).toBe(skipped)
    expect(result.mappings.items.b).toBe(fresh)
  })
})
