import { Logger } from '@freearhey/core'
import { Command } from 'commander'
import { RunLockedError, withRunLock } from '../../lib/server/lock'
import { config } from '../../lib/server/config'
import { runAll } from '../../lib/server/runAll'

const program = new Command()
program.option('-l, --lineup <slug>', 'Run only the given lineup').parse(process.argv)

interface RunOptions {
  lineup?: string
}

const options: RunOptions = program.opts()
const logger = new Logger()

async function main() {
  logger.info('starting...')
  if (options.lineup) logger.info(`lineup: ${options.lineup}`)

  try {
    const { runs } = await withRunLock(config.storageDir, () =>
      runAll({ config, logger, lineup: options.lineup })
    )
    const failed = Object.entries(runs).filter(([, run]) => run.result === 'failed')
    for (const [slug, run] of failed) logger.error(`${slug}: ${run.error}`)
    if (failed.length) process.exitCode = 1
    logger.info('finished')
  } catch (error) {
    if (!(error instanceof RunLockedError)) throw error
    logger.error(error.message)
    process.exitCode = 1
  }
}

main()
