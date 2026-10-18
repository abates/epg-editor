<script lang="ts">
  import type { ChannelRowData } from '$lib/types/channel'

  interface Props {
    row: ChannelRowData
  }

  let { row }: Props = $props()
</script>

<div class="flex items-center gap-2 min-w-0">
  {#if row.logo}
    <img src={row.logo} alt="" class="w-6 h-6 object-contain shrink-0" loading="lazy" />
  {/if}
  <span class="text-sm text-gray-900 dark:text-white font-medium truncate">{row.name}</span>
</div>
