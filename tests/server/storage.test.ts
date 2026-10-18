import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Storage } from '$lib/server/storage'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let storage: Storage

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-storage-'))
  storage = new Storage(rootDir)
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('Storage', () => {
  it('saves and loads text and JSON, creating parent dirs', async () => {
    await storage.save('a/b/file.txt', 'hello')
    await storage.saveJson('a/data.json', { x: 1 })

    expect(await storage.load('a/b/file.txt')).toBe('hello')
    expect(await storage.json('a/data.json')).toEqual({ x: 1 })
    expect(await storage.load('a/data.json')).toBe('{\n  "x": 1\n}\n')
  })

  it('leaves no temp files behind', async () => {
    await storage.save('dir/file.txt', 'one')
    await storage.save('dir/file.txt', 'two')

    expect(await fs.readdir(path.join(rootDir, 'dir'))).toEqual(['file.txt'])
    expect(await storage.load('dir/file.txt')).toBe('two')
  })

  it('keeps the old file when a write fails', async () => {
    await storage.save('dir/file.txt', 'good')
    await fs.chmod(path.join(rootDir, 'dir'), 0o500)
    try {
      await expect(storage.save('dir/file.txt', 'bad')).rejects.toThrow()
    } finally {
      await fs.chmod(path.join(rootDir, 'dir'), 0o700)
    }

    expect(await storage.load('dir/file.txt')).toBe('good')
  })

  it('reports invalid JSON with the file name', async () => {
    await storage.save('broken.json', '{')
    await expect(storage.json('broken.json')).rejects.toThrow('broken.json is not valid JSON')
  })

  it('refuses paths outside the root dir', () => {
    expect(() => storage.path('../outside')).toThrow('outside')
    expect(() => storage.path('/etc/passwd')).toThrow('outside')
    expect(storage.path('..inside')).toBe(path.join(rootDir, '..inside'))
  })

  it('lists dirs, moves and removes', async () => {
    expect(await storage.listDirs('missing')).toEqual([])
    await storage.save('list/one/file.txt', '')
    await storage.save('list/file.txt', '')
    await storage.move('list/one', 'list/two')

    expect(await storage.listDirs('list')).toEqual(['two'])
    await storage.remove('list')
    expect(await storage.exists('list')).toBe(false)
  })
})
