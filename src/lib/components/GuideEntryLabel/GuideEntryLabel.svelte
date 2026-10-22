<script lang="ts">
  import { ProvenanceBadge } from '$lib/components'
  import type { GuideOrigin } from '$lib/types/mapping'

  interface Props {
    entry: {
      site: string
      site_id: string
      xmltv_id: string
      name: string
      origin: GuideOrigin
      logo?: string | null
    }
  }

  let { entry }: Props = $props()
</script>

<div class="flex items-start gap-2 min-w-0">
  {#if entry.logo}
    <img src={entry.logo} alt="" class="w-6 h-6 object-contain shrink-0" loading="lazy" />
  {/if}
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
        · <span
          class="text-amber-600 dark:text-amber-400"
          title="Not in the iptv-org database, so the guide has no logo for it"
        >
          no xmltv_id
        </span>
      {/if}
    </div>
  </div>
</div>
