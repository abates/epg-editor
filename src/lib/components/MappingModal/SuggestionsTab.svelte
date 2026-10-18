<script lang="ts">
  import type { GuideEntryData } from '$lib/types/guide'
  import type { SuggestionData } from '$lib/types/suggestion'
  import { getSuggestions } from '$lib/api'
  import { Alert } from '$lib/components'
  import * as Icon from '$lib/icons'
  import * as MappingModal from './'

  interface Props {
    slug: string
    channelKey: string
    current: { site: string; site_id: string } | null
    saving: boolean
    onPick: (entry: GuideEntryData) => void
  }

  let { slug, channelKey, current, saving, onPick }: Props = $props()

  let suggestions: SuggestionData[] | null = $state(null)
  let error: string | null = $state(null)

  $effect(() => {
    getSuggestions(slug, channelKey)
      .then(result => (suggestions = result))
      .catch(cause => (error = (cause as Error).message))
  })
</script>

<!-- FR-P-3 / FR-P-4: ranked entries with the reasons they matched -->
{#if error}
  <Alert variant="warning">{error}</Alert>
{:else if !suggestions}
  <div class="flex items-center gap-2 py-6 justify-center text-sm text-gray-500 dark:text-gray-400">
    <Icon.Spinner size={18} /> Finding matches…
  </div>
{:else if !suggestions.length}
  <p class="py-6 text-center text-sm text-gray-500 dark:text-gray-400">
    No suggestions. Try the Search tab, or enter the entry by hand.
  </p>
{:else}
  <MappingModal.EntryList
    entries={suggestions.map(suggestion => suggestion.entry)}
    {current}
    disabled={saving}
    {onPick}
  >
    {#snippet details(index)}
      {@const suggestion = suggestions![index]}
      <div class="mt-1 flex flex-wrap gap-1">
        <span class="text-[11px] font-medium text-gray-700 dark:text-gray-200 mr-1">
          score {suggestion.score}
        </span>
        {#each suggestion.reasons as reason (`${reason.kind}:${reason.detail}`)}
          <span
            class="text-[11px] px-1.5 rounded-sm {reason.points < 0
              ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
              : 'bg-gray-100 text-gray-600 dark:bg-primary-750 dark:text-gray-300'}"
          >
            {reason.points > 0 ? '+' : ''}{reason.points}
            {reason.detail}
          </span>
        {/each}
      </div>
    {/snippet}
  </MappingModal.EntryList>
{/if}
