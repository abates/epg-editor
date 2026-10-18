<script lang="ts">
  import type { GuideOrigin } from '$lib/types/mapping'

  interface Props {
    origin: GuideOrigin
  }

  let { origin }: Props = $props()

  const TITLES: Record<GuideOrigin, string> = {
    upstream: 'Entry from iptv-org/epg',
    overlay: 'Entry from a local overlay site',
    manual: 'Entry typed in by hand'
  }
</script>

<!-- FR-P-9 -->
<span
  class="inline-flex items-center h-5 px-1.5 rounded-full border border-gray-200 dark:border-gray-700 text-[11px] text-gray-500 dark:text-gray-300"
  title={TITLES[origin]}
>
  {origin}
</span>
