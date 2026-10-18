<script lang="ts">
  import { ModalContext, MODAL_KEY } from '$lib/modal.svelte'
  import { setContext, tick, type Snippet } from 'svelte'

  interface Props {
    children?: Snippet
    classBg?: string
    classWindowWrap?: string
    classWindow?: string
  }

  let { children, classBg = '', classWindowWrap = '', classWindow = '' }: Props = $props()

  const modal = new ModalContext()
  setContext(MODAL_KEY, modal)

  let scrollContainer: HTMLDivElement | undefined = $state()

  $effect(() => {
    const isOpen = !!modal.isOpen

    if (isOpen) {
      document.documentElement.classList.add('no-scroll')

      const existingModals = document.querySelectorAll('.modal-scroll-container')
      existingModals.forEach(el => {
        if (el !== scrollContainer) {
          ;(el as HTMLElement).style.setProperty('overflow-y', 'hidden', 'important')
        }
      })

      tick().then(() => {
        scrollContainer?.focus()
        scrollContainer?.scrollTo({ top: 0 })
      })
    }

    return () => {
      const remainingModals = Array.from(
        document.querySelectorAll('.modal-scroll-container')
      ) as HTMLElement[]
      const activeModals = remainingModals.filter(el => el !== scrollContainer)

      if (activeModals.length === 0) {
        document.documentElement.classList.remove('no-scroll')
      } else {
        const topMostModal = activeModals[activeModals.length - 1]
        topMostModal.style.setProperty('overflow-y', 'auto', 'important')
        topMostModal.focus()
      }
    }
  })

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === scrollContainer) {
      event.preventDefault()
      modal.close()
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && event.target === scrollContainer) {
      event.preventDefault()
      modal.close()
    }
  }
</script>

{#if modal.isOpen}
  <div
    class="fixed inset-0 bg-black/70 modal-backdrop pointer-events-none {classBg}"
    style="z-index: 9999;"
  ></div>
  <div
    bind:this={scrollContainer}
    onkeydown={handleKeyDown}
    onclick={handleBackdropClick}
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    class="fixed inset-0 h-screen w-screen overflow-y-auto overflow-x-hidden outline-none overscroll-behavior-contain modal-scroll-container"
    style="z-index: 10000; scrollbar-gutter: stable;"
  >
    {#if modal.component}
      {@const Content = modal.component}

      <div class="flex justify-center p-2 pb-20 sm:py-28 pointer-events-none {classWindowWrap}">
        <div class="w-full max-w-3xl pointer-events-none {classWindow}">
          <div class="pointer-events-auto">
            <Content {...modal.props} />
          </div>
        </div>
      </div>
    {/if}
  </div>
{/if}

{@render children?.()}
