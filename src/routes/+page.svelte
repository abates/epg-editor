<script lang="ts">
  import { JobButton, LineupCard, RunResultBadge } from '$lib/components'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data }: PageProps = $props()
</script>

<svelte:head>
  <title>Lineups · epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-7xl flex flex-col gap-4">
  <div class="flex items-center justify-between gap-2">
    <div class="min-w-0">
      <h1 class="text-xl text-gray-900 dark:text-white font-medium">Lineups</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 flex flex-wrap items-center gap-2">
        <a href={resolve('/status')} class="hover:underline">
          Last sync:
          {#if data.sync}{new Date(data.sync.finishedAt).toLocaleString()}{:else}never{/if}
        </a>
        {#if data.sync}<RunResultBadge result={data.sync.result} />{/if}
      </p>
    </div>
    <div class="flex flex-wrap gap-2">
      {#if data.lineups.length}
        <JobButton kind="grab" label="Grab now" />
      {/if}
      <a href={resolve('/lineups/new')} class="btn-primary">
        <Icon.Plus size={16} />
        New lineup
      </a>
    </div>
  </div>

  {#each data.errors as { slug, message } (slug)}
    <div
      class="rounded-md border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300"
    >
      Lineup <span class="font-mono">{slug}</span> could not be loaded: {message}
    </div>
  {/each}

  {#if data.lineups.length}
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {#each data.lineups as { lineup, counts, lastRun } (lineup.slug)}
        <LineupCard {lineup} {counts} {lastRun} />
      {/each}
    </div>
  {:else if !data.errors.length}
    <div
      class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 px-4 py-10 text-center"
    >
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        No lineups yet. Import an M3U playlist, for example your HDHomeRun's
        <span class="font-mono">lineup.m3u</span>, to get started.
      </p>
      <a href={resolve('/lineups/new')} class="btn-primary">
        <Icon.Plus size={16} />
        New lineup
      </a>
    </div>
  {/if}
</div>
