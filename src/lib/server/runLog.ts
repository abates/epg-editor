import { createWriteStream, type WriteStream } from 'node:fs'
import fs from 'node:fs/promises'
import path from 'node:path'

const TAIL_LINES = 50

export interface RunLogger {
  info(message: string): void
  warn(message: string): void
  error(message: string): void
}

// One log file per sync/grab run under /data/logs. Step messages also go to the console
// logger; child process output only goes to the file. Keeps the last lines for status files
export class RunLog {
  readonly filepath: string
  private readonly stream: WriteStream
  private readonly logger?: RunLogger
  private readonly lines: string[] = []

  private constructor(filepath: string, stream: WriteStream, logger?: RunLogger) {
    this.filepath = filepath
    this.stream = stream
    this.logger = logger
  }

  static async open(dir: string, prefix: string, date: Date, logger?: RunLogger): Promise<RunLog> {
    await fs.mkdir(dir, { recursive: true })
    const filepath = path.join(dir, `${prefix}-${date.toISOString().replace(/[:.]/g, '-')}.log`)

    return new RunLog(filepath, createWriteStream(filepath, { flags: 'a' }), logger)
  }

  get name(): string {
    return path.basename(this.filepath)
  }

  get tail(): string[] {
    return [...this.lines]
  }

  info(message: string) {
    this.logger?.info(message)
    this.line(message)
  }

  warn(message: string) {
    this.logger?.warn(message)
    this.line(`warning: ${message}`)
  }

  error(message: string) {
    this.logger?.error(message)
    this.line(`error: ${message}`)
  }

  line(text: string) {
    this.stream.write(`${text}\n`)
    this.lines.push(text)
    if (this.lines.length > TAIL_LINES) this.lines.shift()
  }

  async close(): Promise<void> {
    await new Promise<void>(resolve => this.stream.end(resolve))
  }
}

// Removes all but the newest `keep` logs with the given prefix (names sort by timestamp)
export async function rotateLogs(dir: string, prefix: string, keep: number): Promise<void> {
  const files = (await fs.readdir(dir).catch(() => []))
    .filter(file => file.startsWith(`${prefix}-`) && file.endsWith('.log'))
    .sort()

  for (const file of files.slice(0, Math.max(0, files.length - keep))) {
    await fs.rm(path.join(dir, file), { force: true })
  }
}
