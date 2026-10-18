<script lang="ts">
  import type { ChannelRowData } from '$lib/types/channel'
  import type { SuggestionData } from '$lib/types/suggestion'
  import { StatusBadge } from '$lib/components'

  interface Props {
    row: ChannelRowData
    suggestion?: SuggestionData
  }

  let { row, suggestion }: Props = $props()
</script>

{#if row.mapping?.stale}
  <StatusBadge status="stale" title="The mapped entry no longer exists after the last sync" />
{:else if row.status === 'unmapped' && suggestion}
  <StatusBadge status="suggested" />
{:else}
  <StatusBadge status={row.status} />
{/if}
