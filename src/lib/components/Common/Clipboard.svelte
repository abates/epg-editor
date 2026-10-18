<script lang="ts">
  import { tick, type Snippet } from 'svelte'

  interface Props {
    text: string
    onCopy?: () => void
    children?: Snippet<[{ copy: () => Promise<void> }]>
  }

  const { text, onCopy = () => {}, children }: Props = $props()

  let textarea: HTMLTextAreaElement | undefined = $state()

  async function copy() {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else if (textarea) {
      textarea.select()
      document.execCommand('Copy')
      await tick()
      textarea.blur()
    }
    onCopy()
  }
</script>

{@render children?.({ copy })}
<textarea bind:this={textarea} value={text} aria-hidden="true" tabindex="-1"></textarea>

<style>
  textarea {
    left: 0;
    bottom: 0;
    margin: 0;
    padding: 0;
    opacity: 0;
    width: 1px;
    height: 1px;
    border: none;
    display: block;
    position: absolute;
  }
</style>
