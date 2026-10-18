<script lang="ts">
  import type { GuideEntryData } from '$lib/types/guide'
  import { GuideEntryLabel } from '$lib/components'
  import type { Snippet } from 'svelte'

  interface Props {
    entries: GuideEntryData[]
    current?: { site: string; site_id: string } | null
    disabled?: boolean
    details?: Snippet<[number]>
    onPick: (entry: GuideEntryData) => void
  }

  let { entries, current = null, disabled = false, details, onPick }: Props = $props()

  const isCurrent = (entry: GuideEntryData) =>
    current?.site === entry.site && current?.site_id === entry.site_id
</script>

<ul class="divide-y divide-gray-100 dark:divide-primary-750">
  {#each entries as entry, index (`${entry.site}/${entry.site_id}`)}
    <li class="flex items-start justify-between gap-3 py-2.5">
      <div class="min-w-0 flex-1">
        <GuideEntryLabel {entry} />
        {@render details?.(index)}
      </div>
      {#if isCurrent(entry)}
        <span class="text-xs text-green-700 dark:text-green-300 pt-1">Current</span>
      {:else}
        <button
          type="button"
          class="btn-secondary h-8 px-3 shrink-0"
          {disabled}
          onclick={() => onPick(entry)}
          aria-label="Use {entry.name} from {entry.site}"
        >
          Use
        </button>
      {/if}
    </li>
  {/each}
</ul>
