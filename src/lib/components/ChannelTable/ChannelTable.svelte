<script lang="ts">
  import type { ChannelRowData } from '$lib/types/channel'
  import type { SuggestionData } from '$lib/types/suggestion'
  import * as ChannelTable from './'

  interface Props {
    rows: ChannelRowData[]
    suggestions: Record<string, SuggestionData> | null
    onOpen: (row: ChannelRowData) => void
  }

  let { rows, suggestions, onOpen }: Props = $props()
</script>

<!-- FR-P-1; collapses to cards below `sm` [FR-U-3] -->
<table class="hidden sm:table w-full text-left">
  <thead
    class="text-xs uppercase text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700"
  >
    <tr>
      <th class="py-2 pl-4 pr-2 font-medium w-20">No.</th>
      <th class="py-2 px-2 font-medium">Channel</th>
      <th class="py-2 px-2 font-medium w-28">Status</th>
      <th class="py-2 px-2 font-medium">Guide entry</th>
      <th class="py-2 pl-2 pr-4 w-20"><span class="sr-only">Actions</span></th>
    </tr>
  </thead>
  <tbody>
    {#each rows as row (row.key)}
      {@const suggestion = suggestions?.[row.key]}
      <tr
        class="border-b last:border-b-0 border-gray-100 dark:border-primary-750 hover:bg-gray-50 dark:hover:bg-primary-800 cursor-pointer"
        onclick={() => onOpen(row)}
      >
        <td class="py-2 pl-4 pr-2 font-mono text-sm text-gray-500 dark:text-gray-400">
          {row.number ?? ''}
        </td>
        <td class="py-2 px-2">
          <ChannelTable.ChannelName {row} />
        </td>
        <td class="py-2 px-2"><ChannelTable.ChannelStatus {row} {suggestion} /></td>
        <td class="py-2 px-2 max-w-md"><ChannelTable.ChannelMapping {row} {suggestion} /></td>
        <td class="py-2 pl-2 pr-4 text-right">
          <button
            type="button"
            class="text-sm text-blue-600 dark:text-blue-400 hover:underline cursor-pointer"
            onclick={event => {
              event.stopPropagation()
              onOpen(row)
            }}
            aria-label="{row.status === 'unmapped' ? 'Map' : 'Edit'} {row.name}"
          >
            {row.status === 'unmapped' ? 'Map' : 'Edit'}
          </button>
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<ul class="sm:hidden divide-y divide-gray-100 dark:divide-primary-750">
  {#each rows as row (row.key)}
    {@const suggestion = suggestions?.[row.key]}
    <li>
      <button
        type="button"
        class="w-full text-left px-4 py-3 flex flex-col gap-1.5 hover:bg-gray-50 dark:hover:bg-primary-800 cursor-pointer"
        onclick={() => onOpen(row)}
        aria-label="{row.status === 'unmapped' ? 'Map' : 'Edit'} {row.name}"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="font-mono text-sm text-gray-500 dark:text-gray-400"
              >{row.number ?? ''}</span
            >
            <ChannelTable.ChannelName {row} />
          </div>
          <ChannelTable.ChannelStatus {row} {suggestion} />
        </div>
        <ChannelTable.ChannelMapping {row} {suggestion} />
      </button>
    </li>
  {/each}
</ul>
