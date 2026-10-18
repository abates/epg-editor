# epg-editor — Code & UI Style

Derived from [iptv-org/iptv-org.github.io](https://github.com/iptv-org/iptv-org.github.io) (primary reference — this is a SvelteKit app) and [iptv-org/epg](https://github.com/iptv-org/epg) (server-side libraries and idioms). Where the two disagree, **iptv-org.github.io wins**.

## 1. Tooling

| Tool | Setting |
| --- | --- |
| Node | `>=22`, `.npmrc` → `engine-strict=true` |
| Package type | `"type": "module"` |
| TypeScript | `strict`; `tsconfig.json` extends `./.svelte-kit/tsconfig.json`, `typeRoots` incl. `./src/types` |
| Prettier (`.prettierrc`) | `{"singleQuote": true, "semi": false, "printWidth": 100, "trailingComma": "none", "arrowParens": "avoid", "plugins": ["prettier-plugin-svelte"], "overrides": [{"files": "*.svelte", "options": {"parser": "svelte"}}]}` |
| ESLint (`eslint.config.js`) | flat config: `@eslint/js` recommended + `typescript-eslint` recommended + `eslint-plugin-svelte` recommended; browser+node globals; `projectService` for `.svelte` / `.svelte.ts`; ignore `tests/__data__/**`, `build/**`, `.svelte-kit/**`, `static/**` |
| Line endings | **LF** (site convention; epg's CRLF is *not* adopted). Add `.gitattributes` `* text=auto eol=lf`. |
| Tests | **Vitest**; files `tests/**/*.test.ts`; fixtures `tests/__data__/input` and `tests/__data__/expected` |
| Scripts | CLI scripts in `src/commands/**` run with `tsx`, parsed with `commander`, exposed as `npm run <area>:<verb>` (e.g. `run:all`, `run:sync`, `lineups:export`) |

## 2. TypeScript conventions

- No semicolons, single quotes, 2-space indent, max 100 cols, no trailing commas, `x => x` (no parens for single arg).
- Named exports; barrel `index.ts` per folder (`export { default as Card } from './Card.svelte'`, `export * from './channel'`).
- `interface` for data/props shapes; `*Data` suffix for plain persisted objects (`LineupData`), class of the same base name for the model (`Lineup`) with `toObject()` / `toJSON()`.
- Model classes are thin; logic that can be pure goes in `src/lib/core/*` (easier to test).
- Use `Collection` / `Dictionary` from `@freearhey/core` for list manipulation in server code (as epg does: `.map`, `.filter`, `.keyBy`, `.groupBy`, `.sortBy`, `.uniqBy`, `.all()`). In Svelte components plain arrays are fine.
- Filesystem: `fs-extra` / `node:fs/promises`; Node built-ins with `node:` prefix (`node:path`, `node:child_process`).
- Import order (as seen in both repos): roughly longest-line-first is common upstream but not enforced — do not spend effort reordering; just keep imports grouped (packages, then `$lib`, then relative).
- Errors: throw `Error` with a clear message; commands log with `Logger` from `@freearhey/core` (`logger.info('loading channels...')` — lower-case, trailing `...` for in-progress steps, as in epg).
- Constants in `src/lib/constants.ts` (UPPER_SNAKE) and env parsing only in `src/lib/server/config.ts`.
- No `any`; prefer `unknown` + narrowing.

### Command script shape (epg style)

```ts
import { Logger } from '@freearhey/core'
import { Command } from 'commander'

const program = new Command()
program
  .option('-l, --lineup <slug>', 'Run only the given lineup')
  .parse(process.argv)

interface RunOptions {
  lineup?: string
}

const options: RunOptions = program.opts()
const logger = new Logger()

async function main() {
  logger.info('starting...')
  // ...
}

main()
```

## 3. Svelte conventions (Svelte 5)

- Runes only: `$props()`, `$state()`, `$derived()`, `$effect()`. No legacy `export let`, no Svelte stores for new code.
- `<script lang="ts">` first, then markup, then optional `<style>` (rare — Tailwind first).
- Props typed with an `interface Props` and destructured with defaults:

  ```svelte
  <script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
      border?: boolean
      headerLeft?: Snippet
      body?: Snippet
    }

    let { border = false, headerLeft, body }: Props = $props()
  </script>
  ```

- Slots via **snippets** (`{@render headerLeft?.()}`), event props named `onClick`, `onClose`, `onSubmit` (camelCase callback props, not `createEventDispatcher`).
- Spread `...restProps` onto the root element for components wrapping native elements (`Button`, icons).
- Shared client state as a class with `$state` fields in `*.svelte.ts`, exported as a singleton (`export const darkMode = new DarkModeManager()`), like the site's `darkMode.svelte.ts`, `modal.svelte.ts`.
- Modal via context (`getContext<ModalContext>('modal')` → `modal.open(Component, props)`), ported from the site.
- Toasts: `toast.push(message)` from `@zerodevx/svelte-toast`; options as in the site's `+layout.svelte` (bottom-left, 5 s, `classes: ['custom']`, background `#1e232f`).
- Components: one folder per component under `src/lib/components/<Name>/` with `<Name>.svelte` + `index.ts`; sub-parts live in the same folder and are imported as a namespace (`import * as ChannelCard from './'`).
- Icons: one component per icon in `src/lib/icons/<Name>.svelte` taking `size` and spreading rest props; `fill="currentColor"`; exported from `src/lib/icons/index.ts`.

## 4. Visual language

Port `src/app.css` from iptv-org.github.io as the base:

```css
@import 'tailwindcss';
@custom-variant dark (&:where(.dark, .dark *));
@theme {
  /* --color-primary-950 … --color-primary-50 : hsl(219, 23%, L%) — copy the full ramp */
}
```

| Element | Classes / values |
| --- | --- |
| Page background | `bg-slate-50 dark:bg-primary-900` (match site body) |
| Nav bar | `h-[61px] py-2.5 bg-[#f8fafc] dark:bg-primary-850 text-gray-500 dark:text-gray-400`, bottom border `border-gray-200 dark:border-gray-700` once scrolled; container `max-w-7xl mx-auto px-3` |
| Wordmark | `font-bold font-mono text-[16px] text-[#1f2328] dark:text-[#f8fafc]` — text "epg-editor" with our own simple icon |
| Card | `rounded-md bg-white dark:bg-primary-810`, optional `border border-gray-200 dark:border-gray-700`; header `pt-2 sm:pt-2.5 pl-4 pr-2.5` |
| Title text | `text-gray-900 dark:text-white font-medium` |
| Body text | `text-sm text-gray-500 dark:text-gray-400` |
| Menu/list button | `rounded-md text-sm h-10 px-2 hover:bg-gray-100 dark:hover:bg-primary-750` |
| Badge | `text-xs h-5.5 px-2 py-0.5 rounded-full border border-gray-200 text-gray-500 dark:text-gray-300` |
| Status badges | Mapped = green tint, Suggested = blue tint, Skipped = gray, Unmapped = amber, Stale = red — same pill shape as Badge, tint via `bg-*-50 dark:bg-*-900/30 text-*-700 dark:text-*-300` |
| Theme colour meta | light `#f8fafc`, dark `#1d242f` |
| Font | Tailwind default sans; monospace for IDs (`site_id`, `xmltv_id`) |

Dark mode: class strategy on `<html>`, inline script in `<svelte:head>` of `+layout.svelte` sets the class before paint from `localStorage.theme` or `prefers-color-scheme`; toggle via `darkMode.toggle()` in the nav bar.

Do **not** use the iptv-org logo as this app's logo (it is their brand); credit iptv-org in the footer instead.

## 5. Files & naming

| Kind | Convention | Example |
| --- | --- | --- |
| Svelte component | PascalCase folder + file | `components/MappingModal/MappingModal.svelte` |
| TS module | camelCase | `playlistParser.ts`, `guideIndex.ts` |
| Rune state module | `*.svelte.ts` | `darkMode.svelte.ts` |
| Types | `src/lib/types/<name>.d.ts` | `lineup.d.ts` |
| Tests | mirror source path | `tests/core/playlistParser.test.ts` |
| Fixtures | `tests/__data__/input/<area>/…`, `expected/<area>/…` | `input/m3u/hdhomerun.m3u` |
| npm scripts | `<area>:<verb>` | `run:all`, `run:sync`, `lineups:export` |
| Commits | short imperative subject; Conventional Commits not required | `Add M3U parser` |
