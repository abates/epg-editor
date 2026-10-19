<script lang="ts">
  import { Alert, JobButton, RunLog, RunResultBadge } from '$lib/components'
  import { formatDuration } from '$lib/core/formatDuration'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data }: PageProps = $props()

  const sync = $derived(data.sync)
</script>

<svelte:head>
  <title>Status · epg-editor</title>
</svelte:head>

{#snippet row(label: string, value: string | number | null | undefined, mono = false)}
  <div class="flex flex-col sm:flex-row sm:gap-4 py-1.5">
    <dt class="sm:w-40 shrink-0 text-gray-500 dark:text-gray-400">{label}</dt>
    <dd class="min-w-0 break-words text-gray-900 dark:text-gray-200" class:font-mono={mono}>
      {value ?? '–'}
    </dd>
  </div>
{/snippet}

<div class="mx-auto px-3 py-6 w-full max-w-5xl flex flex-col gap-4">
  <a
    href={resolve('/')}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} /> Lineups
  </a>

  <div class="flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-xl text-gray-900 dark:text-white font-medium">Status</h1>
    <JobButton kind="sync" label="Sync now" />
  </div>

  {#if !sync}
    <Alert>
      iptv-org/epg has not been synced yet. The first sync clones it and can take several minutes.
    </Alert>
  {:else if sync.result === 'failed'}
    <Alert variant="error">
      The last sync failed: {sync.error}. Grabs keep using the previous checkout.
    </Alert>
  {/if}

  <section
    class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 text-sm"
  >
    <h2 class="text-gray-900 dark:text-white font-medium mb-2">epg checkout</h2>
    <dl>
      {@render row('Repository', data.epg.repo, true)}
      {@render row(data.epg.ref ? 'Pinned ref' : 'Branch', data.epg.ref ?? data.epg.branch, true)}
      {@render row('Commit', sync?.commit, true)}
      {@render row('Directory', data.epg.dir, true)}
      {@render row('Schedule', data.schedule, true)}
    </dl>
  </section>

  {#if sync}
    <section
      class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 text-sm"
    >
      <div class="flex items-center gap-2 mb-2">
        <h2 class="text-gray-900 dark:text-white font-medium">Last sync</h2>
        <RunResultBadge result={sync.result} />
      </div>
      <dl>
        {@render row('Finished', new Date(sync.finishedAt).toLocaleString())}
        {@render row('Duration', formatDuration(sync.duration))}
        {@render row(
          'Guide index',
          sync.index ? `${sync.index.entries} entries in ${sync.index.sites} sites` : null
        )}
        {@render row(
          'iptv-org database',
          sync.database ? `${sync.database.channels} channels, ${sync.database.feeds} feeds` : null
        )}
      </dl>
      {#if sync.warnings.length}
        <div class="mt-3">
          <Alert variant="warning">
            <ul class="list-disc pl-5">
              {#each sync.warnings as warning (warning)}
                <li class="break-words">{warning}</li>
              {/each}
            </ul>
          </Alert>
        </div>
      {/if}
    </section>

    <!-- FR-O-5 -->
    <section
      class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 text-sm"
    >
      <h2 class="text-gray-900 dark:text-white font-medium mb-1">Overlay sites</h2>
      <p class="text-gray-500 dark:text-gray-400 mb-2">
        Local sites from <span class="font-mono">{data.epg.overlayDir}</span>, linked into the epg
        checkout on every sync.
      </p>
      {#if sync.overlay.sites.length || sync.overlay.errors.length}
        <ul class="flex flex-col gap-1">
          {#each sync.overlay.sites as site (site.name)}
            <li class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-gray-900 dark:text-gray-200">{site.name}</span>
              {#if site.conflict}
                <span
                  class="inline-flex items-center h-5.5 px-2 py-0.5 rounded-full text-xs bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300"
                  title="An upstream site with the same name is moved aside while this overlay exists"
                  >replaces upstream</span
                >
              {/if}
            </li>
          {/each}
          {#each sync.overlay.errors as siteError (siteError.name)}
            <li class="text-red-700 dark:text-red-300 break-words">
              <span class="font-mono">{siteError.name}</span>: {siteError.message}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-gray-500 dark:text-gray-400">No overlay sites.</p>
      {/if}
      {#if sync.index?.errors.length}
        <p class="mt-3 text-gray-900 dark:text-white font-medium">Index errors</p>
        <ul class="list-disc pl-5 text-red-700 dark:text-red-300">
          {#each sync.index.errors as indexError (indexError.file)}
            <li class="break-words">
              <span class="font-mono">{indexError.file}</span>: {indexError.message}
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <RunLog title="Sync log · {sync.log}" lines={sync.logTail} />
  {/if}
</div>
