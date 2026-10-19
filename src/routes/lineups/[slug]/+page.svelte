<script lang="ts">
  import {
    Alert,
    BulkAcceptModal,
    ChannelsXmlModal,
    ChannelTable,
    MappingModal,
    SearchField
  } from '$lib/components'
  import type { ChannelRowData } from '$lib/types/channel'
  import type { SuggestionData } from '$lib/types/suggestion'
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { countChannels } from '$lib/core/channelRows'
  import { getSuggestions } from '$lib/api'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import { getContext } from 'svelte'
  import type { PageProps } from './$types'

  type Filter = 'all' | 'mapped' | 'suggested' | 'skipped' | 'unmapped' | 'stale'

  let { data }: PageProps = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)

  // Updated in place after each save; reset when the page data reloads
  let rows = $derived(data.rows)
  let suggestions: Record<string, SuggestionData> | null = $state(null)
  let filter: Filter = $state('all')
  let query = $state('')

  $effect(() => {
    suggestions = null
    data.suggestions.then(result => (suggestions = result))
  })

  const counts = $derived(countChannels(rows))
  const suggestedCount = $derived(
    rows.filter(row => row.status === 'unmapped' && suggestions?.[row.key]).length
  )

  const FILTERS: { id: Filter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'mapped', label: 'Mapped' },
    { id: 'suggested', label: 'Suggested' },
    { id: 'unmapped', label: 'Unmapped' },
    { id: 'skipped', label: 'Skipped' },
    { id: 'stale', label: 'Stale' }
  ]

  function countFor(id: Filter): number {
    if (id === 'all') return counts.total
    if (id === 'suggested') return suggestedCount

    return counts[id]
  }

  // FR-P-2: status filter and free-text search
  const visible = $derived.by(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)

    return rows.filter(row => {
      if (filter === 'stale' && !row.mapping?.stale) return false
      if (filter === 'suggested' && (row.status !== 'unmapped' || !suggestions?.[row.key]))
        return false
      if (['mapped', 'skipped', 'unmapped'].includes(filter) && row.status !== filter) return false

      const guide = row.mapping?.guide
      const text = [row.number, row.name, row.key, guide?.name, guide?.site_id, guide?.xmltv_id]
        .join(' ')
        .toLowerCase()

      return words.every(word => text.includes(word))
    })
  })

  // FR-P-7: the suggested channels in the current filter and search
  const acceptable = $derived(
    visible.flatMap(row => {
      const suggestion = row.status === 'unmapped' ? suggestions?.[row.key] : undefined
      return suggestion ? [{ row, suggestion }] : []
    })
  )

  function replaceRows(updated: ChannelRowData[]) {
    const byKey = new Map(updated.map(row => [row.key, row]))
    rows = rows.map(current => byKey.get(current.key) ?? current)
  }

  function openBulkAccept() {
    modal.open(BulkAcceptModal, {
      slug: data.lineup.slug,
      candidates: acceptable,
      onSaved: replaceRows
    })
  }

  // A cleared channel had no suggestion computed at page load
  async function loadSuggestion(key: string) {
    if (!suggestions || suggestions[key]) return
    const [top] = await getSuggestions(data.lineup.slug, key).catch(() => [])
    if (top && suggestions) suggestions = { ...suggestions, [key]: top }
  }

  function open(row: ChannelRowData) {
    modal.open(MappingModal, {
      slug: data.lineup.slug,
      row,
      filters: data.lineup.filters,
      sites: data.sites,
      onSaved: (updated: ChannelRowData) => {
        replaceRows([updated])
        if (updated.status === 'unmapped') loadSuggestion(updated.key)
      }
    })
  }
</script>

<svelte:head>
  <title>{data.lineup.name} · epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-7xl flex flex-col gap-4">
  <a
    href={resolve('/')}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} /> Lineups
  </a>

  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="min-w-0">
      <h1 class="text-xl text-gray-900 dark:text-white font-medium break-words">
        {data.lineup.name}
      </h1>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        {counts.total} channels · {counts.mapped} in channels.xml
      </p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        class="btn-secondary"
        onclick={() => modal.open(ChannelsXmlModal, { slug: data.lineup.slug })}
      >
        <Icon.Code size={16} /> channels.xml
      </button>
      <a href={resolve('/lineups/[slug]/runs', { slug: data.lineup.slug })} class="btn-secondary">
        <Icon.Play size={16} /> Runs
      </a>
      <a
        href={resolve('/lineups/[slug]/settings', { slug: data.lineup.slug })}
        class="btn-secondary"
      >
        <Icon.Settings size={16} /> Settings
      </a>
    </div>
  </div>

  {#if data.warnings.length}
    <Alert variant="warning">
      <p class="font-medium">The playlist was imported with warnings:</p>
      <ul class="list-disc pl-5">
        {#each data.warnings as warning (warning)}
          <li>{warning}</li>
        {/each}
      </ul>
    </Alert>
  {/if}

  <div class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700">
    <div class="p-3 sm:p-4 flex flex-col gap-3 border-b border-gray-200 dark:border-gray-700">
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
        {#each FILTERS as { id, label } (id)}
          <button
            type="button"
            class="h-8 px-3 rounded-full text-sm border cursor-pointer {filter === id
              ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
              : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-primary-750'}"
            aria-pressed={filter === id}
            onclick={() => (filter = id)}
          >
            {label}
            <span class="ml-1 font-medium">
              {#if id === 'suggested' && !suggestions}…{:else}{countFor(id)}{/if}
            </span>
          </button>
        {/each}
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div class="flex-1 min-w-48">
          <SearchField bind:value={query} placeholder="Search channels" version="mini" />
        </div>
        <button
          type="button"
          class="btn-secondary h-8 px-3"
          disabled={!acceptable.length}
          title={suggestions
            ? 'Review and accept the top suggestion for the channels listed below'
            : 'Suggestions are still loading'}
          onclick={openBulkAccept}
        >
          <Icon.Check size={16} /> Accept suggestions
          {#if acceptable.length}<span class="font-medium">{acceptable.length}</span>{/if}
        </button>
      </div>
    </div>

    {#if visible.length}
      <ChannelTable rows={visible} {suggestions} onOpen={open} />
    {:else}
      <p class="px-4 py-10 text-center text-sm text-gray-500 dark:text-gray-400">
        No channels match.
      </p>
    {/if}
  </div>
</div>
