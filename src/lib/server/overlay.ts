import type { OverlayReportData } from '$lib/types/sync'
import { isValidSlug } from '$lib/core/slug'
import fs from 'node:fs/promises'
import path from 'node:path'

// Local sites in the overlay dir are symlinked into <epg>/sites so `grab` finds them [FR-O-2].
// Their configs only resolve epg's node_modules if the grab runs with NODE_PRESERVE_SYMLINKS=1
// (docs/spikes/M2-overlay-symlinks.md)
export class Overlay {
  readonly overlayDir: string
  readonly sitesDir: string
  readonly shadowDir: string

  constructor(options: { overlayDir: string; sitesDir: string; shadowDir: string }) {
    this.overlayDir = path.resolve(options.overlayDir)
    this.sitesDir = path.resolve(options.sitesDir)
    this.shadowDir = path.resolve(options.shadowDir)
  }

  // Removes every link and moves shadowed upstream sites back, leaving the checkout as git
  // left it [FR-O-3]. Upstream has no symlinks in sites/, so every symlink there is ours
  async remove(): Promise<void> {
    for (const name of await readdir(this.sitesDir)) {
      const target = path.join(this.sitesDir, name)
      if ((await lstat(target))?.isSymbolicLink()) await fs.unlink(target)
    }

    for (const name of await readdir(this.shadowDir)) {
      const shadowed = path.join(this.shadowDir, name)
      const target = path.join(this.sitesDir, name)
      if ((await lstat(this.sitesDir))?.isDirectory() && !(await lstat(target))) {
        await fs.rename(shadowed, target)
      } else {
        await fs.rm(shadowed, { recursive: true, force: true })
      }
    }
  }

  // Overlay sites win over upstream sites of the same name; those are moved to the shadow dir
  async apply(): Promise<OverlayReportData> {
    const report: OverlayReportData = { sites: [], errors: [] }

    for (const name of (await readdir(this.overlayDir)).sort()) {
      if (name.startsWith('.')) continue
      const source = path.join(this.overlayDir, name)
      if (!(await stat(source))?.isDirectory()) continue

      if (!isValidSlug(name)) {
        report.errors.push({
          name,
          message: 'invalid site name: use lower-case letters, digits, "." and "-"'
        })
        continue
      }
      if (!(await stat(path.join(source, `${name}.config.js`)))?.isFile()) {
        report.errors.push({ name, message: `missing ${name}.config.js` })
        continue
      }

      const target = path.join(this.sitesDir, name)
      const existing = await lstat(target)
      let conflict = false
      if (existing?.isSymbolicLink()) {
        await fs.unlink(target)
      } else if (existing) {
        const shadowed = path.join(this.shadowDir, name)
        await fs.mkdir(this.shadowDir, { recursive: true })
        await fs.rm(shadowed, { recursive: true, force: true })
        await fs.rename(target, shadowed)
        conflict = true
      }

      await fs.symlink(source, target, 'dir')
      report.sites.push({ name, conflict })
    }

    return report
  }
}

async function readdir(dir: string): Promise<string[]> {
  try {
    return await fs.readdir(dir)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

async function lstat(filepath: string) {
  return fs.lstat(filepath).catch(ignoreNotFound)
}

async function stat(filepath: string) {
  return fs.stat(filepath).catch(ignoreNotFound)
}

function ignoreNotFound(error: NodeJS.ErrnoException): null {
  if (error.code === 'ENOENT') return null
  throw error
}
