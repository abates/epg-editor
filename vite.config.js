import { sveltekit } from '@sveltejs/kit/vite'
import tailwindcss from '@tailwindcss/vite'
import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  test: {
    include: ['tests/**/*.test.ts'],
    // Opt-in, needs network: npm run test:integration
    exclude: [...configDefaults.exclude, 'tests/integration/**'],
    passWithNoTests: true
  }
})
