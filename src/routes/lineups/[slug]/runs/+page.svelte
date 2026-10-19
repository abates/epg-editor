<script lang="ts">
  import { Alert, CopyToClipboard, JobButton, RunLog, RunResultBadge } from '$lib/components'
  import { formatDuration } from '$lib/core/formatDuration'
  import { resolve } from '$app/paths'
  import { page } from '$app/state'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data }: PageProps = $props()

  const lineup = $derived(data.lineup)
  const guideUrl = $derived(`${page.url.origin}/guides/${lineup.slug}.xml`)
  const logHref = (log: string) =>
    `${resolve('/lineups/[slug]/runs', { slug: lineup.slug })}?${new URLSearchParams({ log })}`
</script>

<svelte:head>
  <title>Runs · {lineup.name} · epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-7xl flex flex-col gap-4">
  <a
    href={resolve('/lineups/[slug]', { slug: lineup.slug })}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} />
    {lineup.name}
  </a>

  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <h1 class="text-xl text-gray-900 dark:text-white font-medium">Runs</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        The last 20 grabs of {lineup.name}.
        {#if !lineup.grab.enabled}Scheduled grabs are off for this lineup.{/if}
      </p>
    </div>
    <JobButton kind="grab" lineup={lineup.slug} label="Grab now" variant="primary" />
  </div>

  <!-- FR-R-5 -->
  <div
    class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 flex flex-col gap-2 text-sm"
  >
    <p class="text-gray-900 dark:text-white font-medium">Guide</p>
    {#if data.guides.xml}
      <div class="flex items-center gap-1 min-w-0">
        <code
          class="min-w-0 truncate text-xs text-gray-500 bg-gray-100 dark:text-gray-300 dark:bg-primary-750 px-2 py-1 rounded-sm font-mono"
          title={guideUrl}>{guideUrl}</code
        >
        <CopyToClipboard text={guideUrl} title="Copy guide URL" />
      </div>
      <div class="flex flex-wrap gap-3 text-gray-500 dark:text-gray-400">
        <a class="underline" href="/guides/{lineup.slug}.xml" target="_blank" rel="noreferrer"
          >{lineup.slug}.xml</a
        >
        {#if data.guides.gz}
          <a class="underline" href="/guides/{lineup.slug}.xml.gz">{lineup.slug}.xml.gz</a>
        {/if}
      </div>
    {:else}
      <p class="text-gray-500 dark:text-gray-400">
        No guide yet. It is published at <span class="font-mono">{guideUrl}</span> after the first successful
        grab.
      </p>
    {/if}
  </div>

  {#if data.runs.length}
    <div
      class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 overflow-x-auto"
    >
      <table class="w-full text-sm">
        <thead class="text-left text-xs text-gray-500 dark:text-gray-400">
          <tr class="border-b border-gray-200 dark:border-gray-700">
            <th class="px-4 py-2 font-medium">Started</th>
            <th class="px-4 py-2 font-medium">Result</th>
            <th class="px-4 py-2 font-medium">Duration</th>
            <th class="px-4 py-2 font-medium text-right">Channels</th>
            <th class="px-4 py-2 font-medium text-right">Programmes</th>
            <th class="px-4 py-2 font-medium">Log</th>
          </tr>
        </thead>
        <tbody class="text-gray-700 dark:text-gray-300">
          {#each data.runs as run (run.startedAt)}
            <tr
              class="border-b last:border-b-0 border-gray-100 dark:border-gray-700/50 align-top"
              class:bg-gray-50={run.log === data.log?.name}
              class:dark:bg-primary-750={run.log === data.log?.name}
            >
              <td class="px-4 py-2 whitespace-nowrap">
                {new Date(run.startedAt).toLocaleString()}
              </td>
              <td class="px-4 py-2">
                <RunResultBadge result={run.result} />
                {#if run.error}
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400 break-words">
                    {run.error}
                  </p>
                {/if}
              </td>
              <td class="px-4 py-2 whitespace-nowrap">{formatDuration(run.duration)}</td>
              <td class="px-4 py-2 text-right">{run.channels ?? '–'}</td>
              <td class="px-4 py-2 text-right">{run.programs ?? '–'}</td>
              <td class="px-4 py-2">
                {#if run.log}
                  <a class="underline whitespace-nowrap" href={logHref(run.log)}>View</a>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <Alert>No grabs yet. Use "Grab now", or wait for the next scheduled run.</Alert>
  {/if}

  {#if data.log}
    <RunLog title={data.log.name} lines={data.log.lines} />
  {/if}
</div>
