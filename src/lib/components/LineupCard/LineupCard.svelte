<script lang="ts">
  import { CopyToClipboard, IconButton, RunResultBadge, StatusBadge } from '$lib/components'
  import type { ChannelCountsData } from '$lib/types/channel'
  import type { LineupData } from '$lib/types/lineup'
  import type { RunData } from '$lib/types/run'
  import { goto } from '$app/navigation'
  import { resolve } from '$app/paths'
  import { page } from '$app/state'

  interface Props {
    lineup: LineupData
    counts: ChannelCountsData
    lastRun: RunData | null
  }

  let { lineup, counts, lastRun }: Props = $props()

  const guideUrl = $derived(`${page.url.origin}/guides/${lineup.slug}.xml`)
</script>

<!-- FR-L-2 -->
<div
  class="min-w-0 rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 flex flex-col gap-3"
>
  <div class="flex items-start justify-between gap-2">
    <div class="min-w-0">
      <a
        href={resolve('/lineups/[slug]', { slug: lineup.slug })}
        class="text-gray-900 dark:text-white font-medium hover:underline break-words"
      >
        {lineup.name}
      </a>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        {counts.total} channels
        {#if !lineup.grab.enabled}· not in scheduled grabs{/if}
      </p>
    </div>
    <IconButton
      title="Settings for {lineup.name}"
      iconName="Settings"
      onClick={() => goto(resolve('/lineups/[slug]/settings', { slug: lineup.slug }))}
    />
  </div>

  <div class="flex flex-wrap gap-1.5">
    <StatusBadge status="mapped" count={counts.mapped} />
    <StatusBadge status="skipped" count={counts.skipped} />
    <StatusBadge status="unmapped" count={counts.unmapped} />
    {#if counts.stale}
      <StatusBadge status="stale" count={counts.stale} />
    {/if}
  </div>

  <div class="flex flex-wrap items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
    <a href={resolve('/lineups/[slug]/runs', { slug: lineup.slug })} class="hover:underline">
      Last grab:
      {#if lastRun}{new Date(lastRun.startedAt).toLocaleString()}{:else}never{/if}
    </a>
    {#if lastRun}
      <RunResultBadge result={lastRun.result} title={lastRun.error ?? undefined} />
    {/if}
  </div>

  <div class="flex items-center gap-1 min-w-0">
    <code
      class="min-w-0 truncate text-xs text-gray-500 bg-gray-100 dark:text-gray-300 dark:bg-primary-750 px-2 py-1 rounded-sm font-mono"
      title={guideUrl}
    >
      {guideUrl}
    </code>
    <CopyToClipboard text={guideUrl} title="Copy guide URL" />
  </div>
</div>
