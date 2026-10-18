import { Logger } from '@freearhey/core'
import { Command } from 'commander'

// Placeholder: lock → sync → grab every enabled lineup (M5)
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
  logger.info('not implemented yet')
}

main()
