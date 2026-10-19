<script lang="ts">
  import type { RunResult } from '$lib/types/run'

  interface Props {
    result: RunResult
    title?: string
  }

  let { result, title }: Props = $props()

  const LABELS: Record<RunResult, string> = {
    success: 'Success',
    failed: 'Failed',
    skipped: 'Skipped'
  }

  const TINTS: Record<RunResult, string> = {
    success: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    failed: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300',
    skipped: 'bg-gray-100 dark:bg-gray-800/50 text-gray-600 dark:text-gray-300'
  }
</script>

<span
  class="inline-flex items-center h-5.5 px-2 py-0.5 rounded-full text-xs whitespace-nowrap {TINTS[
    result
  ]}"
  {title}
>
  {LABELS[result]}
</span>
