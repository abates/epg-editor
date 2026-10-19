<script lang="ts">
  import { IconButton } from '$lib/components'
  import { darkMode } from '$lib/darkMode.svelte'
  import { REPO_URL } from '$lib/constants'
  import { resolve } from '$app/paths'
  import { onMount } from 'svelte'
  import * as NavBar from './'

  let scrollY = $state(0)

  function openGitHub() {
    window.open(REPO_URL, '_blank', 'noreferrer')
  }

  onMount(() => {
    darkMode.init()
  })
</script>

<svelte:window bind:scrollY />

<nav
  class="sticky top-0 z-10 py-2.5 w-full h-[61px] bg-[#f8fafc] dark:bg-primary-850 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700"
  class:border-b={scrollY > 0}
>
  <div class="flex justify-between items-center mx-auto px-3 w-full max-w-7xl">
    <a href={resolve('/')} class="pr-2">
      <NavBar.Logo />
    </a>

    <div class="inline-flex items-center sm:space-x-1">
      <a
        href={resolve('/status')}
        class="px-2 text-sm hover:text-gray-900 dark:hover:text-white hover:underline">Status</a
      >
      <IconButton
        onClick={() => darkMode.toggle()}
        title="Toggle Dark Mode"
        iconName={darkMode.isActive ? 'LightMode' : 'DarkMode'}
        iconSize={20}
      />
      <IconButton onClick={openGitHub} title="GitHub" iconName="GitHub" iconSize={20} />
    </div>
  </div>
</nav>
