<script lang="ts">
  import type { BadgeStatus } from '$lib/types/channel'

  interface Props {
    status: BadgeStatus
    count?: number
    title?: string
  }

  let { status, count, title }: Props = $props()

  const LABELS: Record<BadgeStatus, string> = {
    mapped: 'Mapped',
    suggested: 'Suggested',
    skipped: 'Skipped',
    unmapped: 'Unmapped',
    stale: 'Stale'
  }

  const TINTS: Record<BadgeStatus, string> = {
    mapped: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    suggested: 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    skipped: 'bg-gray-100 dark:bg-gray-800/50 text-gray-600 dark:text-gray-300',
    unmapped: 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
    stale: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
  }
</script>

<span
  class="inline-flex items-center h-5.5 px-2 py-0.5 rounded-full text-xs whitespace-nowrap {TINTS[
    status
  ]}"
  {title}
>
  {LABELS[status]}
  {#if count !== undefined}<span class="ml-1 font-medium">{count}</span>{/if}
</span>
