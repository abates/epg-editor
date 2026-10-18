<script lang="ts">
  import type { GuideEntryData } from '$lib/types/guide'
  import { Alert, SearchField } from '$lib/components'
  import { searchEntries } from '$lib/api'
  import * as MappingModal from './'

  interface Props {
    initialQuery: string
    sites: string[]
    country: string
    current: { site: string; site_id: string } | null
    saving: boolean
    onPick: (entry: GuideEntryData) => void
  }

  let { initialQuery, sites, country: initialCountry, current, saving, onPick }: Props = $props()

  // svelte-ignore state_referenced_locally
  let query = $state(initialQuery)
  let site = $state('')
  // svelte-ignore state_referenced_locally
  let country = $state(initialCountry)
  let lang = $state('')
  let entries: GuideEntryData[] = $state([])
  let searching = $state(false)
  let error: string | null = $state(null)

  // Debounced; a newer search makes the results of an older one irrelevant
  let latest = 0
  $effect(() => {
    const filters = { site, country: country.trim().toLowerCase(), lang: lang.trim() }
    const text = query
    const id = ++latest
    const timer = setTimeout(async () => {
      searching = true
      try {
        const result = await searchEntries(text, filters)
        if (id === latest) {
          entries = result
          error = null
        }
      } catch (cause) {
        if (id === latest) error = (cause as Error).message
      } finally {
        if (id === latest) searching = false
      }
    }, 250)

    return () => clearTimeout(timer)
  })
</script>

<!-- FR-P-4: search over all guide entries, filterable by site, country and language -->
<div class="flex flex-col gap-3">
  <SearchField bind:value={query} isSearching={searching} placeholder="Channel name" />
  <div class="grid grid-cols-3 gap-2">
    <select bind:value={site} class="field" aria-label="Site">
      <option value="">All sites</option>
      {#each sites as name (name)}
        <option value={name}>{name}</option>
      {/each}
    </select>
    <input
      bind:value={country}
      class="field font-mono"
      placeholder="Country"
      aria-label="Country"
    />
    <input bind:value={lang} class="field font-mono" placeholder="Language" aria-label="Language" />
  </div>

  {#if error}
    <Alert variant="warning">{error}</Alert>
  {:else if entries.length}
    <MappingModal.EntryList {entries} {current} disabled={saving} {onPick} />
  {:else if !searching}
    <p class="py-6 text-center text-sm text-gray-500 dark:text-gray-400">No matching entries.</p>
  {/if}
</div>
