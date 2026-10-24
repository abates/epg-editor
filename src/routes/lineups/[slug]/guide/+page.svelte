<script lang="ts">
  import { Alert, GuideGrid, JobButton } from '$lib/components'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data }: PageProps = $props()

  const lineup = $derived(data.lineup)
  const guide = $derived(data.guide)
</script>

<svelte:head>
  <title>Guide · {lineup.name} · epg-editor</title>
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
      <h1 class="text-xl text-gray-900 dark:text-white font-medium">Guide</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        {#if guide}
          What the last successful grab produced, generated {new Date(
            guide.generatedAt
          ).toLocaleString()}.
        {:else}
          What the last successful grab produced.
        {/if}
      </p>
    </div>
    <div class="flex flex-wrap gap-2">
      <JobButton kind="grab" lineup={lineup.slug} label="Grab now" variant="primary" />
      <a href={resolve('/lineups/[slug]/runs', { slug: lineup.slug })} class="btn-secondary">
        <Icon.Play size={16} /> Runs
      </a>
    </div>
  </div>

  {#if !guide}
    <Alert>No guide yet. Use "Grab now", or wait for the next scheduled run.</Alert>
  {:else if !guide.channels.length}
    <Alert>The guide has no channels. Map and grab this lineup to see programme data here.</Alert>
  {:else}
    <div
      class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700"
    >
      {#if guide.range}
        <GuideGrid channels={guide.channels} range={guide.range} />
      {:else}
        <p class="px-4 py-10 text-center text-sm text-gray-500 dark:text-gray-400">
          The guide has channels but no programme data yet.
        </p>
      {/if}
    </div>
  {/if}
</div>
