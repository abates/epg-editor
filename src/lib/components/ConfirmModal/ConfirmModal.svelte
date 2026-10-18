<script lang="ts">
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { getContext } from 'svelte'

  interface Props {
    title: string
    message: string
    confirmLabel?: string
    onConfirm: () => void
  }

  let { title, message, confirmLabel = 'Delete', onConfirm }: Props = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)
</script>

<div
  class="mx-auto max-w-md rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-5 flex flex-col gap-4"
>
  <h2 class="text-gray-900 dark:text-white font-medium">{title}</h2>
  <p class="text-sm text-gray-500 dark:text-gray-400">{message}</p>
  <div class="flex justify-end gap-2">
    <button type="button" class="btn-secondary" onclick={() => modal.close()}>Cancel</button>
    <button
      type="button"
      class="btn-danger"
      onclick={() => {
        modal.close()
        onConfirm()
      }}
    >
      {confirmLabel}
    </button>
  </div>
</div>
