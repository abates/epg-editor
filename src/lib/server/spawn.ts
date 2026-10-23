import spawn from 'nano-spawn'

// FR-R-4: child processes only see these variables, so none of ours (STORAGE_DIR, EPG_*, npm_*)
// leak into epg, which reads DATA_DIR, SITES_DIR, ROOT_DIR, etc.
const ENV_ALLOWLIST = [
  'PATH',
  'HOME',
  'USER',
  'LANG',
  'LC_ALL',
  'TZ',
  'TMPDIR',
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'NO_PROXY',
  'http_proxy',
  'https_proxy',
  'no_proxy'
]

export interface RunCommandOptions {
  cwd: string
  env?: Record<string, string>
  onLine?: (line: string) => void
}

export function sanitizedEnv(
  extra: Record<string, string> = {},
  source: NodeJS.ProcessEnv = process.env
): Record<string, string> {
  const env: Record<string, string> = {}
  for (const name of ENV_ALLOWLIST) {
    const value = source[name]
    if (value !== undefined) env[name] = value
  }

  return { ...env, ...extra }
}

// Runs a command with an argument array (never a shell) and a sanitised env [NFR-SEC-4].
// stdout and stderr lines go to onLine as they arrive; the combined output is returned.
// nano-spawn's rejection only names the exit code, since iterating the lines (above) stops it
// from buffering its own copy of stdout/stderr — so on failure the lines collected here are
// appended to the error instead, letting callers match on the command's actual output [issue #7]
export async function runCommand(
  file: string,
  args: string[],
  options: RunCommandOptions
): Promise<string> {
  const subprocess = spawn(file, args, {
    cwd: options.cwd,
    env: childEnv(options.env ?? sanitizedEnv()),
    stdin: 'ignore'
  })

  const lines: string[] = []
  try {
    for await (const line of subprocess) {
      lines.push(line)
      options.onLine?.(line)
    }
    await subprocess
  } catch (error) {
    throw withOutput(error, lines)
  }

  return lines.join('\n')
}

function withOutput(error: unknown, lines: string[]): Error {
  if (!(error instanceof Error) || lines.length === 0) {
    return error instanceof Error ? error : new Error(String(error))
  }

  return new Error(`${error.message}\n${lines.join('\n')}`, { cause: error })
}

// nano-spawn always merges `env` over process.env. Node drops keys whose value is undefined,
// so every inherited variable is set to undefined first and only `env` reaches the child
function childEnv(env: Record<string, string>): Record<string, string | undefined> {
  const result: Record<string, string | undefined> = {}
  for (const name of Object.keys(process.env)) result[name] = undefined

  return { ...result, ...env }
}
