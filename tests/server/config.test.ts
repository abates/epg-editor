import { loadConfig } from '$lib/server/config'
import { describe, expect, it } from 'vitest'

describe('loadConfig', () => {
  it('uses the documented defaults', () => {
    expect(loadConfig({})).toEqual({
      storageDir: '/data',
      overlayDir: '/data/sites',
      epg: { repo: 'https://github.com/iptv-org/epg.git', branch: 'master', ref: null },
      cronSchedule: '0 0 * * *',
      runAtStartup: true,
      grab: { days: null, maxConnections: 1, delay: 0, timeout: 30000, gzip: true }
    })
  })

  it('reads overrides from the environment', () => {
    const config = loadConfig({
      STORAGE_DIR: '/srv/epg',
      EPG_REF: 'v1.2.3',
      RUN_AT_STARTUP: 'false',
      GRAB_DAYS: '3',
      GRAB_GZIP: '0'
    })

    expect(config.storageDir).toBe('/srv/epg')
    expect(config.overlayDir).toBe('/srv/epg/sites')
    expect(config.epg.ref).toBe('v1.2.3')
    expect(config.runAtStartup).toBe(false)
    expect(config.grab.days).toBe(3)
    expect(config.grab.gzip).toBe(false)
  })

  it('treats blank values as unset', () => {
    expect(loadConfig({ EPG_REF: '  ', GRAB_DAYS: '' }).epg.ref).toBeNull()
  })

  it('rejects invalid values', () => {
    expect(() => loadConfig({ GRAB_TIMEOUT: '30s' })).toThrow('GRAB_TIMEOUT')
    expect(() => loadConfig({ GRAB_GZIP: 'maybe' })).toThrow('GRAB_GZIP')
  })
})
