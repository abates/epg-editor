<script lang="ts">
  import { ProvenanceBadge } from '$lib/components'
  import type { GuideOrigin } from '$lib/types/mapping'

  interface Props {
    entry: { site: string; site_id: string; xmltv_id: string; name: string; origin: GuideOrigin }
  }

  let { entry }: Props = $props()
</script>

<div class="min-w-0">
  <div class="flex items-center gap-1.5 min-w-0">
    <span class="text-sm text-gray-900 dark:text-white truncate" title={entry.name}>
      {entry.name}
    </span>
    <ProvenanceBadge origin={entry.origin} />
  </div>
  <div class="text-xs text-gray-500 dark:text-gray-400 font-mono break-all">
    {entry.site} · {entry.site_id}
    {#if entry.xmltv_id}
      · {entry.xmltv_id}
    {:else}
      · <span class="text-amber-600 dark:text-amber-400" title="The guide will use the site ID">
        no xmltv_id
      </span>
    {/if}
  </div>
</div>
