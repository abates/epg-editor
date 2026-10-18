import { afterEach, describe, expect, it } from 'vitest'
import { runCommand, sanitizedEnv } from '$lib/server/spawn'

const printEnv = 'console.log(JSON.stringify(process.env))'

afterEach(() => {
  delete process.env.STORAGE_DIR
  delete process.env.EPG_TEST_SECRET
})

describe('sanitizedEnv', () => {
  it('keeps only allow-listed variables plus extras', () => {
    const env = sanitizedEnv(
      { GIT_TERMINAL_PROMPT: '0' },
      { PATH: '/bin', HOME: '/home/node', STORAGE_DIR: '/data', SITES_DIR: './x' }
    )

    expect(env).toEqual({ PATH: '/bin', HOME: '/home/node', GIT_TERMINAL_PROMPT: '0' })
  })
})

describe('runCommand', () => {
  it('does not pass this process environment to the child', async () => {
    process.env.STORAGE_DIR = '/data'
    process.env.EPG_TEST_SECRET = 'secret'

    const output = await runCommand(process.execPath, ['-e', printEnv], {
      cwd: process.cwd(),
      env: sanitizedEnv({ EXTRA: 'yes' })
    })
    const env = JSON.parse(output)

    expect(env.STORAGE_DIR).toBeUndefined()
    expect(env.EPG_TEST_SECRET).toBeUndefined()
    expect(env.EXTRA).toBe('yes')
    expect(env.PATH).toBe(process.env.PATH)
  })

  it('passes stdout and stderr lines to onLine and returns the output', async () => {
    const lines: string[] = []
    const output = await runCommand(
      process.execPath,
      ['-e', 'console.log("one"); console.error("two"); console.log("three")'],
      { cwd: process.cwd(), onLine: line => lines.push(line) }
    )

    expect(lines.sort()).toEqual(['one', 'three', 'two'])
    expect(output.split('\n').sort()).toEqual(['one', 'three', 'two'])
  })

  it('does not interpret arguments with a shell', async () => {
    const output = await runCommand(
      process.execPath,
      ['-e', 'console.log(process.argv[1])', '$(echo hi); rm -rf /'],
      { cwd: process.cwd() }
    )

    expect(output).toBe('$(echo hi); rm -rf /')
  })

  it('rejects when the command exits with an error', async () => {
    await expect(
      runCommand(process.execPath, ['-e', 'process.exit(3)'], { cwd: process.cwd() })
    ).rejects.toThrow(/exit code 3/)
  })
})
