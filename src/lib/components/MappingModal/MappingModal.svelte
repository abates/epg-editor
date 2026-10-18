<script lang="ts">
  import type { GuideEntryField, GuideEntryInput } from '$lib/core/mappingValidation'
  import type { ChannelRowData } from '$lib/types/channel'
  import type { LineupFiltersData } from '$lib/types/lineup'
  import type { MappingRequestData } from '$lib/types/mapping'
  import type { GuideEntryData } from '$lib/types/guide'
  import { clearMapping, saveMapping, type MappingResponse } from '$lib/api'
  import { GuideEntryLabel, IconButton, StatusBadge } from '$lib/components'
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { toast } from '@zerodevx/svelte-toast'
  import { getContext } from 'svelte'
  import * as MappingModal from './'

  type Tab = 'suggestions' | 'search' | 'manual'

  interface Props {
    slug: string
    row: ChannelRowData
    filters: LineupFiltersData
    sites: string[]
    onSaved: (row: ChannelRowData, warnings: string[]) => void
  }

  let { slug, row, filters, sites, onSaved }: Props = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)
  const guide = $derived(row.mapping?.guide ?? null)

  // svelte-ignore state_referenced_locally
  let tab: Tab = $state(row.mapping?.guide?.origin === 'manual' ? 'manual' : 'suggestions')
  let saving = $state(false)
  let errors: Partial<Record<GuideEntryField, string>> = $state({})

  const manualInitial: GuideEntryInput = $derived(
    guide
      ? { site: guide.site, site_id: guide.site_id, lang: guide.lang, xmltv_id: guide.xmltv_id }
      : {
          site: filters.preferredSites[0] ?? '',
          site_id: '',
          lang: filters.languages[0] ?? 'en',
          xmltv_id: ''
        }
  )

  const TABS: { id: Tab; label: string }[] = [
    { id: 'suggestions', label: 'Suggestions' },
    { id: 'search', label: 'Search' },
    { id: 'manual', label: 'Manual' }
  ]

  // Every change is saved at once [FR-P-6]
  async function run(action: () => Promise<MappingResponse | null>, message: string) {
    saving = true
    try {
      const result = await action()
      if (!result) return
      onSaved(result.row, result.warnings)
      toast.push(message)
      for (const warning of result.warnings) toast.push(warning)
      modal.close()
    } catch (cause) {
      toast.push((cause as Error).message)
    } finally {
      saving = false
    }
  }

  async function save(request: MappingRequestData): Promise<MappingResponse | null> {
    const result = await saveMapping(slug, request)
    if (result.ok) return result

    errors = result.errors
    return null
  }

  function pick(entry: GuideEntryData) {
    const request = {
      key: row.key,
      status: 'mapped' as const,
      entry: { site: entry.site, site_id: entry.site_id }
    }
    run(() => save(request), `${row.name} mapped to ${entry.name}`)
  }

  function saveManual(entry: GuideEntryInput) {
    errors = {}
    const request = { key: row.key, status: 'mapped' as const, manual: entry }
    run(() => save(request), `${row.name} mapped by hand`)
  }

  function skip() {
    run(() => save({ key: row.key, status: 'skipped' }), `${row.name} skipped`)
  }

  function clear() {
    run(() => clearMapping(slug, row.key), `${row.name} cleared`)
  }
</script>

<!-- FR-P-4 / FR-P-5 -->
<div class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700">
  <div class="flex items-start justify-between gap-2 pt-3 pl-4 pr-2.5">
    <div class="min-w-0">
      <h2 class="text-gray-900 dark:text-white font-medium">
        <span class="font-mono text-gray-500 dark:text-gray-400 mr-1">{row.number ?? ''}</span>
        {row.name}
      </h2>
      <p class="text-xs text-gray-500 dark:text-gray-400 font-mono">key {row.key}</p>
    </div>
    <IconButton title="Close" iconName="Close" onClick={() => modal.close()} />
  </div>

  <div class="px-4 pt-3">
    <div
      class="rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 flex items-center gap-3"
    >
      {#if row.mapping?.stale}
        <StatusBadge status="stale" title="The mapped entry no longer exists after the last sync" />
      {:else}
        <StatusBadge status={row.status} />
      {/if}
      {#if guide}
        <GuideEntryLabel entry={guide} />
      {:else if row.status === 'skipped'}
        <span class="text-sm text-gray-500 dark:text-gray-400">Left out of channels.xml</span>
      {:else}
        <span class="text-sm text-gray-500 dark:text-gray-400">Not mapped yet</span>
      {/if}
    </div>
  </div>

  <div class="px-4 pt-3 border-b border-gray-200 dark:border-gray-700 flex gap-4" role="tablist">
    {#each TABS as { id, label } (id)}
      <button
        type="button"
        role="tab"
        aria-selected={tab === id}
        class="pb-2 -mb-px text-sm border-b-2 cursor-pointer {tab === id
          ? 'border-blue-500 text-gray-900 dark:text-white'
          : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
        onclick={() => (tab = id)}
      >
        {label}
      </button>
    {/each}
  </div>

  <div class="px-4 py-3 min-h-48" role="tabpanel">
    {#if tab === 'suggestions'}
      <MappingModal.SuggestionsTab
        {slug}
        channelKey={row.key}
        current={guide}
        {saving}
        onPick={pick}
      />
    {:else if tab === 'search'}
      <MappingModal.SearchTab
        initialQuery={row.name}
        {sites}
        country={filters.countries[0] ?? ''}
        current={guide}
        {saving}
        onPick={pick}
      />
    {:else}
      <MappingModal.ManualTab
        {sites}
        initial={manualInitial}
        {errors}
        {saving}
        onSubmit={saveManual}
      />
    {/if}
  </div>

  <div
    class="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex flex-wrap justify-end gap-2"
  >
    {#if row.status !== 'skipped'}
      <button type="button" class="btn-secondary" disabled={saving} onclick={skip}>
        Skip channel
      </button>
    {/if}
    {#if row.status !== 'unmapped'}
      <button type="button" class="btn-secondary" disabled={saving} onclick={clear}>
        Clear mapping
      </button>
    {/if}
  </div>
</div>
