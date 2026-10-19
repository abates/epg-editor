import { sveltekit } from '@sveltejs/kit/vite'
import { defineConfig } from 'vitest/config'

// ARCHITECTURE §8: clones iptv-org/epg and runs a real grab, so it is kept out of `npm test`
export default defineConfig({
  plugins: [sveltekit()],
  test: {
    include: ['tests/integration/**/*.test.ts'],
    testTimeout: 60_000
  }
})
