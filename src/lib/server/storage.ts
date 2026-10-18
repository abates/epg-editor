import writeFileAtomic from 'write-file-atomic'
import fs from 'node:fs/promises'
import path from 'node:path'

// File access under one root dir. Every write is atomic (temp file + rename) [NFR-REL-1]
export class Storage {
  readonly rootDir: string

  constructor(rootDir: string) {
    this.rootDir = path.resolve(rootDir)
  }

  path(...segments: string[]): string {
    const filepath = path.resolve(this.rootDir, ...segments)
    const relative = path.relative(this.rootDir, filepath)
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
      throw new Error(`path "${segments.join('/')}" is outside ${this.rootDir}`)
    }

    return filepath
  }

  async exists(filepath: string): Promise<boolean> {
    try {
      await fs.access(this.path(filepath))
      return true
    } catch {
      return false
    }
  }

  async load(filepath: string): Promise<string> {
    return fs.readFile(this.path(filepath), 'utf8')
  }

  async json<T>(filepath: string): Promise<T> {
    const content = await this.load(filepath)
    try {
      return JSON.parse(content) as T
    } catch (error) {
      throw new Error(`${filepath} is not valid JSON: ${(error as Error).message}`, {
        cause: error
      })
    }
  }

  async save(filepath: string, content: string): Promise<void> {
    const abspath = this.path(filepath)
    await fs.mkdir(path.dirname(abspath), { recursive: true })
    await writeFileAtomic(abspath, content, { encoding: 'utf8' })
  }

  async saveJson(filepath: string, data: unknown): Promise<void> {
    await this.save(filepath, JSON.stringify(data, null, 2) + '\n')
  }

  async listDirs(dir: string): Promise<string[]> {
    try {
      const entries = await fs.readdir(this.path(dir), { withFileTypes: true })
      return entries.filter(entry => entry.isDirectory()).map(entry => entry.name)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
      throw error
    }
  }

  async createDir(dir: string): Promise<void> {
    await fs.mkdir(this.path(dir), { recursive: true })
  }

  async move(from: string, to: string): Promise<void> {
    const target = this.path(to)
    await fs.mkdir(path.dirname(target), { recursive: true })
    await fs.rename(this.path(from), target)
  }

  async remove(filepath: string): Promise<void> {
    await fs.rm(this.path(filepath), { recursive: true, force: true })
  }
}
