<script lang="ts">
  interface Props {
    size: number
    class?: string
  }

  let { size, ...restProps }: Props = $props()
</script>

<svg
  {...restProps}
  width={size}
  height={size}
  fill="currentColor"
  viewBox="0 0 20 20"
  xmlns="http://www.w3.org/2000/svg"
>
  <rect x="5" y="1.5" width="1.5" height="3.5" rx="0.75"></rect>
  <rect x="13.5" y="1.5" width="1.5" height="3.5" rx="0.75"></rect>
  <rect x="2" y="3.5" width="16" height="14.5" rx="2"></rect>
</svg>
