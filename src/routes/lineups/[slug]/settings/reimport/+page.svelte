<script lang="ts">
  import { Alert } from '$lib/components'
  import { enhance } from '$app/forms'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data }: PageProps = $props()

  const diff = $derived(data.diff)
  const unchanged = $derived(!diff.added.length && !diff.removed.length && !diff.renamed.length)
  const removedMapped = $derived(Object.keys(data.removedMappings).length)
  let busy = $state(false)
</script>

<svelte:head>
  <title>Review playlist · {data.lineup.name} · epg-editor</title>
</svelte:head>

<!-- FR-M-6 -->
<div class="mx-auto px-3 py-6 w-full max-w-3xl flex flex-col gap-4">
  <a
    href={resolve('/lineups/[slug]/settings', { slug: data.lineup.slug })}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} /> Settings
  </a>
  <h1 class="text-xl text-gray-900 dark:text-white font-medium">Review the new playlist</h1>
  <p class="text-sm text-gray-500 dark:text-gray-400">
    {#if data.source.type === 'url'}
      Fetched from <span class="font-mono break-all">{data.source.url}</span>.
    {:else}
      Uploaded file.
    {/if}
    {diff.unchanged} channels are unchanged and keep their mappings.
  </p>

  {#if data.warnings.length}
    <Alert variant="warning">
      <ul class="list-disc pl-5">
        {#each data.warnings as warning (warning)}<li>{warning}</li>{/each}
      </ul>
    </Alert>
  {/if}

  {#if unchanged}
    <Alert variant="info">No channels were added, removed or renamed.</Alert>
  {/if}

  {#snippet section(
    title: string,
    tint: string,
    items: { key: string; number: string | null; text: string }[]
  )}
    {#if items.length}
      <div
        class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700"
      >
        <h2 class="px-4 pt-3 pb-2 font-medium {tint}">{title} ({items.length})</h2>
        <ul class="divide-y divide-gray-100 dark:divide-primary-750">
          {#each items as item (item.key)}
            <li class="px-4 py-2 flex gap-3 text-sm">
              <span class="w-14 font-mono text-gray-500 dark:text-gray-400"
                >{item.number ?? ''}</span
              >
              <span class="text-gray-900 dark:text-white">{item.text}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/snippet}

  {@render section(
    'Added',
    'text-green-700 dark:text-green-300',
    diff.added.map(channel => ({ ...channel, text: channel.name }))
  )}
  {@render section(
    'Renamed',
    'text-blue-700 dark:text-blue-300',
    diff.renamed.map(channel => ({ ...channel, text: `${channel.from} → ${channel.to}` }))
  )}
  {@render section(
    'Removed',
    'text-red-700 dark:text-red-300',
    diff.removed.map(channel => ({
      ...channel,
      text: data.removedMappings[channel.key]
        ? `${channel.name} (${data.removedMappings[channel.key]})`
        : channel.name
    }))
  )}

  <div class="flex flex-wrap items-center justify-end gap-3">
    <form method="POST" action="?/discard" use:enhance>
      <button type="submit" class="btn-secondary" disabled={busy}>Discard</button>
    </form>
    <form
      method="POST"
      action="?/apply"
      class="flex flex-wrap items-center gap-3"
      use:enhance={() => {
        busy = true
        return async ({ update }) => {
          await update()
          busy = false
        }
      }}
    >
      {#if removedMapped}
        <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input type="checkbox" name="dropRemoved" checked />
          Delete the mappings of {removedMapped} removed
          {removedMapped === 1 ? 'channel' : 'channels'}
        </label>
      {/if}
      <button type="submit" class="btn-primary" disabled={busy}>
        {#if busy}<Icon.Spinner size={16} />{/if}
        Apply new playlist
      </button>
    </form>
  </div>
</div>
