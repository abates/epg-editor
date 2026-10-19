// Modelled on iptv-org/epg's pm2.config.js: the web server, a chronos scheduler and an optional
// run at startup [FR-R-1]. Runs share one lock (/data/run.lock), so they never overlap
const fs = require('node:fs')
const path = require('node:path')

const storageDir = process.env.STORAGE_DIR || '/data'
const schedule = process.env.CRON_SCHEDULE || '0 0 * * *'
const runAtStartup = !['false', '0', 'no'].includes(
  (process.env.RUN_AT_STARTUP || 'true').trim().toLowerCase()
)

const apps = [
  {
    name: 'web',
    script: 'build/index.js',
    exec_mode: 'fork',
    instances: 1,
    watch: false,
    autorestart: true,
    // "Grab now" / "Sync now" runs are detached children of the web process and must survive
    // a web restart
    treekill: false
  },
  {
    name: 'scheduler',
    script: 'node_modules/@freearhey/chronos/index.js',
    args: ['--execute', 'npm run run:all', '--pattern', schedule, '--log'],
    exec_mode: 'fork',
    instances: 1,
    watch: false,
    autorestart: true
  }
]

if (runAtStartup) {
  // run:all syncs first, so it also covers the first clone
  apps.push({
    name: 'startup',
    script: 'npm',
    args: ['run', 'run:all'],
    interpreter: 'none',
    exec_mode: 'fork',
    instances: 1,
    watch: false,
    autorestart: false,
    max_restarts: 1
  })
} else if (!fs.existsSync(path.join(storageDir, 'epg'))) {
  // NFR-DEP-3: the first clone runs in the background while the UI shows "initialising"
  apps.push({
    name: 'init',
    script: 'npm',
    args: ['run', 'run:sync'],
    interpreter: 'none',
    exec_mode: 'fork',
    instances: 1,
    watch: false,
    autorestart: false,
    max_restarts: 1
  })
}

module.exports = { apps }
