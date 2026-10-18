import { Logger } from '@freearhey/core'
import { Command } from 'commander'
import { RunLockedError, withRunLock } from '../../lib/server/lock'
import { config } from '../../lib/server/config'
import { runSync } from '../../lib/server/sync'

const program = new Command()
program.parse(process.argv)
const logger = new Logger()

async function main() {
  logger.info('starting...')

  try {
    const status = await withRunLock(config.storageDir, () => runSync({ config, logger }))
    if (status.result === 'failed') process.exitCode = 1
  } catch (error) {
    if (!(error instanceof RunLockedError)) throw error
    logger.error(error.message)
    process.exitCode = 1
  }
}

main()
