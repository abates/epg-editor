import { Logger } from '@freearhey/core'
import { Command } from 'commander'

// Placeholder: lock → clone/pull epg, install, link overlay sites (M2)
const program = new Command()
program.parse(process.argv)
const logger = new Logger()

async function main() {
  logger.info('starting...')

  logger.info('not implemented yet')
}

main()
