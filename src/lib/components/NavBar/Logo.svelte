<script lang="ts">
  interface Props {
    size?: number
  }

  let { size = 28 }: Props = $props()
</script>

<div class="flex items-center space-x-2 text-[#1f2328] dark:text-[#f8fafc]">
  <svg
    height={size}
    width={size}
    viewBox="0 0 32 32"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <rect
      x="2"
      y="4"
      width="28"
      height="24"
      rx="4"
      stroke="currentColor"
      stroke-width="2.5"
      fill="none"
    />
    <rect x="7" y="10" width="7" height="3" rx="1.5" fill="currentColor" />
    <rect x="16" y="10" width="9" height="3" rx="1.5" fill="currentColor" />
    <rect x="7" y="15" width="11" height="3" rx="1.5" fill="currentColor" />
    <rect x="20" y="15" width="5" height="3" rx="1.5" fill="currentColor" />
    <rect x="7" y="20" width="5" height="3" rx="1.5" fill="currentColor" />
    <rect x="14" y="20" width="11" height="3" rx="1.5" fill="currentColor" />
  </svg><span class="font-bold font-mono text-[16px] dark:text-[#f8fafc] antialiased"
    >epg-editor</span
  >
</div>
