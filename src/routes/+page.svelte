<script lang="ts">
  import { Card } from '$lib/components'
</script>

<svelte:head>
  <title>epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-7xl">
  <Card border>
    {#snippet headerLeft()}
      <h1 class="text-gray-900 dark:text-white font-medium">Lineups</h1>
    {/snippet}
    {#snippet body()}
      <p class="px-4 pt-2 pb-4 text-sm text-gray-500 dark:text-gray-400">No lineups yet.</p>
    {/snippet}
  </Card>
</div>
