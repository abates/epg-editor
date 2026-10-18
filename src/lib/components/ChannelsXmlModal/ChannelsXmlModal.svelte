<script lang="ts">
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { Alert, IconButton } from '$lib/components'
  import * as Icon from '$lib/icons'
  import { getContext } from 'svelte'

  interface Props {
    slug: string
  }

  let { slug }: Props = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)
  let xml: string | null = $state(null)
  let error: string | null = $state(null)

  $effect(() => {
    fetch(`/lineups/${slug}/channels.xml`)
      .then(response => {
        if (!response.ok) throw new Error(`Loading channels.xml failed: HTTP ${response.status}`)
        return response.text()
      })
      .then(text => (xml = text))
      .catch(cause => (error = (cause as Error).message))
  })
</script>

<!-- FR-X-6: read-only preview -->
<div class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700">
  <div class="flex items-center justify-between gap-2 pt-2.5 pl-4 pr-2.5">
    <h2 class="text-gray-900 dark:text-white font-medium font-mono">channels.xml</h2>
    <div class="flex items-center gap-1">
      <a
        href="/lineups/{slug}/channels.xml?download"
        class="btn-secondary h-8 px-3"
        data-sveltekit-reload
      >
        <Icon.Download size={16} /> Download
      </a>
      <IconButton title="Close" iconName="Close" onClick={() => modal.close()} />
    </div>
  </div>
  <div class="p-4">
    {#if error}
      <Alert variant="error">{error}</Alert>
    {:else if xml === null}
      <div class="flex justify-center py-6 text-gray-500"><Icon.Spinner size={18} /></div>
    {:else}
      <pre
        class="overflow-x-auto max-h-[60vh] text-xs font-mono text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-primary-850 rounded-md p-3">{xml}</pre>
    {/if}
  </div>
</div>
