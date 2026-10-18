<script lang="ts">
  import type { ChannelRowData } from '$lib/types/channel'
  import type { SuggestionData } from '$lib/types/suggestion'
  import { GuideEntryLabel } from '$lib/components'

  interface Props {
    row: ChannelRowData
    suggestion?: SuggestionData
  }

  let { row, suggestion }: Props = $props()
</script>

{#if row.mapping?.guide}
  <GuideEntryLabel entry={row.mapping.guide} />
{:else if row.status === 'skipped'}
  <span class="text-sm text-gray-400 dark:text-gray-500">Not in the guide</span>
{:else if suggestion}
  <div class="text-sm text-gray-500 dark:text-gray-400 truncate">
    {suggestion.entry.name}
    <span class="text-xs font-mono">· {suggestion.entry.site}</span>
  </div>
{:else}
  <span class="text-sm text-gray-400 dark:text-gray-500">—</span>
{/if}
