<script lang="ts">
  interface Props {
    lines: string[]
    title?: string
  }

  let { lines, title }: Props = $props()
</script>

<!-- FR-R-6: tail of a sync or grab log -->
<div class="flex flex-col gap-1 min-w-0">
  {#if title}
    <p class="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">{title}</p>
  {/if}
  <pre
    class="max-h-[32rem] overflow-auto rounded-md bg-gray-100 dark:bg-primary-750 text-gray-700 dark:text-gray-300 text-xs font-mono p-3 whitespace-pre-wrap break-words">{lines.join(
      '\n'
    ) || 'The log is empty.'}</pre>
</div>
