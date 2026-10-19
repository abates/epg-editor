<script lang="ts">
  import type { JobKind } from '$lib/types/run'
  import { jobs } from '$lib/jobs.svelte'
  import * as Icon from '$lib/icons'

  interface Props {
    kind: JobKind
    lineup?: string
    label: string
    variant?: 'primary' | 'secondary'
  }

  let { kind, lineup, label, variant = 'secondary' }: Props = $props()

  const busy = $derived(jobs.running || jobs.starting)
</script>

<!-- FR-R-3: disabled while any sync or grab runs, since they exclude each other -->
<button
  type="button"
  class={variant === 'primary' ? 'btn-primary' : 'btn-secondary'}
  disabled={busy}
  title={jobs.running ? 'A sync or grab is already running' : undefined}
  onclick={() => jobs.start(kind, lineup)}
>
  {#if busy}
    <Icon.Spinner size={16} />
  {:else if kind === 'sync'}
    <Icon.Refresh size={16} />
  {:else}
    <Icon.Play size={16} />
  {/if}
  {label}
</button>
