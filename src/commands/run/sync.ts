import { Logger } from '@freearhey/core'
import { Command } from 'commander'
import { RunLockedError, withRunLock } from '../../lib/server/lock'
import { clearCurrentRun, writeCurrentRun } from '../../lib/server/runHistory'
import { config } from '../../lib/server/config'
import { Storage } from '../../lib/server/storage'
import { runSync } from '../../lib/server/sync'

const program = new Command()
program.parse(process.argv)
const logger = new Logger()

async function main() {
  logger.info('starting...')

  try {
    const storage = new Storage(config.storageDir)
    const status = await withRunLock(config.storageDir, async () => {
      await writeCurrentRun(storage, { step: 'sync', lineup: null })
      try {
        return await runSync({ config, logger })
      } finally {
        await clearCurrentRun(storage)
      }
    })
    if (status.result === 'failed') process.exitCode = 1
  } catch (error) {
    if (!(error instanceof RunLockedError)) throw error
    logger.error(error.message)
    process.exitCode = 1
  }
}

main()
