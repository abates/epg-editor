<script lang="ts">
  import type { ChannelRowData } from '$lib/types/channel'
  import type { SuggestionData } from '$lib/types/suggestion'
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { Alert, GuideEntryLabel, IconButton } from '$lib/components'
  import { acceptEntries } from '$lib/api'
  import { toast } from '@zerodevx/svelte-toast'
  import { SvelteSet } from 'svelte/reactivity'
  import { getContext } from 'svelte'

  // Call sign (40) plus country (10), or a full name match plus country
  const DEFAULT_MIN_SCORE = 50

  interface Props {
    slug: string
    candidates: { row: ChannelRowData; suggestion: SuggestionData }[]
    onSaved: (rows: ChannelRowData[]) => void
  }

  let { slug, candidates, onSaved }: Props = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)

  let minScore = $state(DEFAULT_MIN_SCORE)
  let saving = $state(false)
  let error: string | null = $state(null)
  const selected = new SvelteSet(keysAtLeast(DEFAULT_MIN_SCORE))

  function keysAtLeast(score: number): string[] {
    return candidates
      .filter(candidate => candidate.suggestion.score >= score)
      .map(candidate => candidate.row.key)
  }

  function selectOnly(keys: string[]) {
    selected.clear()
    for (const key of keys) selected.add(key)
  }

  function toggle(key: string, checked: boolean) {
    if (checked) selected.add(key)
    else selected.delete(key)
  }

  // FR-P-7: nothing is applied until the user confirms the reviewed selection
  async function accept() {
    saving = true
    error = null
    try {
      const items = candidates
        .filter(candidate => selected.has(candidate.row.key))
        .map(({ row, suggestion: { entry } }) => ({
          key: row.key,
          entry: { site: entry.site, site_id: entry.site_id }
        }))
      const result = await acceptEntries(slug, { items })
      onSaved(result.rows)
      toast.push(`${result.rows.length} channels mapped`)
      for (const warning of result.warnings) toast.push(warning)
      modal.close()
    } catch (cause) {
      error = (cause as Error).message
    } finally {
      saving = false
    }
  }
</script>

<!-- FR-P-7 -->
<div class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700">
  <div class="flex items-start justify-between gap-2 pt-3 pl-4 pr-2.5">
    <div class="min-w-0">
      <h2 class="text-gray-900 dark:text-white font-medium">Accept suggestions</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        Review the top suggestion for each channel. Only the ticked channels are mapped.
      </p>
    </div>
    <IconButton title="Close" iconName="Close" onClick={() => modal.close()} />
  </div>

  <div
    class="px-4 py-3 flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-gray-200 dark:border-gray-700"
  >
    <div>
      <label for="min-score" class="field-label">Minimum score</label>
      <input
        id="min-score"
        type="number"
        step="5"
        class="field w-28"
        bind:value={minScore}
        oninput={() => selectOnly(keysAtLeast(Number(minScore) || 0))}
      />
    </div>
    <div class="flex gap-3 h-10 items-center text-sm">
      <button
        type="button"
        class="text-blue-600 dark:text-blue-400 hover:underline cursor-pointer"
        onclick={() => selectOnly(candidates.map(candidate => candidate.row.key))}
      >
        Select all
      </button>
      <button
        type="button"
        class="text-blue-600 dark:text-blue-400 hover:underline cursor-pointer"
        onclick={() => selected.clear()}
      >
        Select none
      </button>
    </div>
    <p class="h-10 flex items-center ml-auto text-sm text-gray-500 dark:text-gray-400">
      {selected.size} of {candidates.length} selected
    </p>
  </div>

  <ul class="max-h-[55vh] overflow-y-auto divide-y divide-gray-100 dark:divide-primary-750">
    {#each candidates as { row, suggestion } (row.key)}
      <li>
        <label
          class="px-4 py-2 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-primary-800"
        >
          <input
            type="checkbox"
            checked={selected.has(row.key)}
            disabled={saving}
            onchange={event => toggle(row.key, event.currentTarget.checked)}
          />
          <div class="w-40 shrink-0 min-w-0">
            <span class="font-mono text-sm text-gray-500 dark:text-gray-400 mr-1">
              {row.number ?? ''}
            </span>
            <span class="text-sm text-gray-900 dark:text-white">{row.name}</span>
          </div>
          <div class="flex-1 min-w-0">
            <GuideEntryLabel entry={suggestion.entry} />
          </div>
          <span
            class="shrink-0 text-xs font-medium {suggestion.score >= minScore
              ? 'text-gray-700 dark:text-gray-200'
              : 'text-amber-600 dark:text-amber-400'}"
            title={suggestion.reasons.map(reason => reason.detail).join(', ')}
          >
            score {suggestion.score}
          </span>
        </label>
      </li>
    {/each}
  </ul>

  {#if error}
    <div class="px-4 pt-3"><Alert variant="error">{error}</Alert></div>
  {/if}

  <div
    class="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex flex-wrap justify-end gap-2"
  >
    <button type="button" class="btn-secondary" disabled={saving} onclick={() => modal.close()}>
      Cancel
    </button>
    <button type="button" class="btn-primary" disabled={saving || !selected.size} onclick={accept}>
      Accept {selected.size}
    </button>
  </div>
</div>
