<script lang="ts">
  import { SvelteToast } from '@zerodevx/svelte-toast'
  import { Modal, NavBar } from '$lib/components'
  import { IPTV_ORG_EPG_URL } from '$lib/constants'
  import { jobs } from '$lib/jobs.svelte'
  import * as Icon from '$lib/icons'
  import type { LayoutProps } from './$types'
  import '../app.css'

  let { data, children }: LayoutProps = $props()

  $effect(() => {
    jobs.set(data.job)
  })

  const toastOptions = {
    duration: 5000,
    reversed: true,
    intro: { x: -192 },
    dismissable: false,
    classes: ['custom']
  }
</script>

<svelte:head>
  <script>
    if (document) {
      const prefersColorScheme = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      const mode = localStorage.theme || prefersColorScheme
      if (mode === 'dark') {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    }
  </script>
</svelte:head>

<Modal>
  <div class="flex flex-col min-h-screen">
    <NavBar />
    {#if !data.indexReady}
      <div
        class="bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 text-sm border-b border-amber-200 dark:border-amber-900"
      >
        <div class="mx-auto px-3 py-2 w-full max-w-7xl">
          The guide index is initialising: iptv-org/epg is being downloaded and indexed. Lineups can
          be imported now; suggestions and search work once it has finished.
        </div>
      </div>
    {/if}
    {#if jobs.running}
      <div
        class="bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200 text-sm border-b border-blue-200 dark:border-blue-900"
        role="status"
      >
        <div class="mx-auto px-3 py-2 w-full max-w-7xl flex items-center gap-2">
          <Icon.Spinner size={14} />
          {#if jobs.current?.step === 'grab'}
            Grabbing <span class="font-mono">{jobs.current.lineup}</span>…
          {:else if jobs.current?.step === 'sync'}
            Syncing iptv-org/epg…
          {:else}
            A sync or grab is running…
          {/if}
        </div>
      </div>
    {/if}
    <main class="grow">
      {@render children?.()}
    </main>
    <footer class="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
      Guide data and grabbers by
      <a class="underline" href={IPTV_ORG_EPG_URL} target="_blank" rel="noreferrer">iptv-org/epg</a>
    </footer>
  </div>
</Modal>

<div class="text-sm">
  <SvelteToast options={toastOptions} />
</div>

<style>
  :root {
    --toastContainerTop: auto;
    --toastContainerRight: auto;
    --toastContainerBottom: 2rem;
    --toastContainerLeft: 1rem;
  }

  :global(.custom) {
    --toastMinHeight: auto;
    --toastBackground: #1e232f;
    --toastMsgPadding: 12px 12px;
    --toastBarHeight: 0;
    --toastBorderRadius: 0.375rem;
  }
</style>
