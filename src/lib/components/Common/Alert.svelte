<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    variant?: 'error' | 'warning' | 'info'
    children?: Snippet
  }

  let { variant = 'info', children }: Props = $props()

  const CLASSES = {
    error:
      'border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300',
    warning:
      'border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200',
    info: 'border-blue-200 dark:border-blue-900 bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200'
  }
</script>

<div
  class="rounded-md border px-4 py-3 text-sm {CLASSES[variant]}"
  role={variant === 'error' ? 'alert' : 'status'}
>
  {@render children?.()}
</div>
