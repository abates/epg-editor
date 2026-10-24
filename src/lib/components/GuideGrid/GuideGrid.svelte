<script lang="ts">
  import type { GuideViewChannelData, GuideViewRangeData } from '$lib/types/guideView'
  import { onDestroy } from 'svelte'

  interface Props {
    channels: GuideViewChannelData[]
    range: GuideViewRangeData
  }

  let { channels, range }: Props = $props()

  const PX_PER_MIN = 6 // 360px/hour
  const ROW_HEIGHT = 64
  const HEADER_HEIGHT = 40
  const LEFT_COL_WIDTH = 192
  const MIN_BLOCK_WIDTH = 24
  const SCROLL_BUFFER_PX = 800 // render ~2h of extra programmes past each visible edge

  // Local-time hour boundaries, so the grid starts/ends on a clean hour line. Times in `range`
  // (and every programme) are already absolute instants parsed from the XMLTV UTC offset, so
  // every `Date` method below reads in the browser's local time for free
  const timelineStart = $derived(floorToHour(new Date(range.start)))
  const timelineEnd = $derived(ceilToHour(new Date(range.stop)))
  const totalMinutes = $derived(
    Math.max(60, (timelineEnd.getTime() - timelineStart.getTime()) / 60000)
  )
  const totalWidthPx = $derived(totalMinutes * PX_PER_MIN)

  interface Block {
    title: string
    tooltip: string
    leftPx: number
    widthPx: number
    startMs: number
    stopMs: number
  }

  // Precomputed once per guide load; cheap enough even for a large multi-day lineup
  const rows = $derived(
    channels.map(channel => ({
      channel,
      blocks: channel.programs.map(toBlock).sort((a, b) => a.startMs - b.startMs)
    }))
  )

  const hourTicks = $derived.by(() => {
    const ticks: { leftPx: number; time: string; date: string | null }[] = []
    for (let t = timelineStart.getTime(); t < timelineEnd.getTime(); t += 60 * 60 * 1000) {
      const date = new Date(t)
      ticks.push({
        leftPx: ((t - timelineStart.getTime()) / 60000) * PX_PER_MIN,
        time: date.toLocaleTimeString([], { hour: 'numeric' }),
        date:
          date.getHours() === 0
            ? date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
            : null
      })
    }
    return ticks
  })

  let scrollEl: HTMLDivElement | undefined = $state()
  let scrollLeft = $state(0)
  let viewportWidth = $state(0)
  let now = $state(Date.now())
  let scrollPending = false

  // Only the programmes within the visible time window (+ a buffer) are rendered, so a guide
  // spanning many channels/days doesn't put thousands of blocks in the DOM at once
  function handleScroll() {
    if (scrollPending || !scrollEl) return
    scrollPending = true
    requestAnimationFrame(() => {
      scrollLeft = scrollEl?.scrollLeft ?? 0
      scrollPending = false
    })
  }

  const timelineScrollPx = $derived(Math.max(0, scrollLeft - LEFT_COL_WIDTH))
  const windowStartMs = $derived(
    timelineStart.getTime() + ((timelineScrollPx - SCROLL_BUFFER_PX) / PX_PER_MIN) * 60000
  )
  const windowEndMs = $derived(
    timelineStart.getTime() +
      ((timelineScrollPx + viewportWidth + SCROLL_BUFFER_PX) / PX_PER_MIN) * 60000
  )

  function visible(blocks: Block[]): Block[] {
    return blocks.filter(block => block.stopMs > windowStartMs && block.startMs < windowEndMs)
  }

  const nowLeftPx = $derived(
    now >= timelineStart.getTime() && now <= timelineEnd.getTime()
      ? ((now - timelineStart.getTime()) / 60000) * PX_PER_MIN
      : null
  )

  function jumpToNow() {
    if (nowLeftPx === null || !scrollEl) return
    scrollEl.scrollTo({
      left: Math.max(0, LEFT_COL_WIDTH + nowLeftPx - viewportWidth / 2),
      behavior: 'smooth'
    })
  }

  function toBlock(program: GuideViewChannelData['programs'][number]): Block {
    const startMs = new Date(program.start).getTime()
    const stopMs = Math.max(new Date(program.stop).getTime(), startMs)
    const leftPx = ((startMs - timelineStart.getTime()) / 60000) * PX_PER_MIN
    const widthPx = Math.max(MIN_BLOCK_WIDTH, ((stopMs - startMs) / 60000) * PX_PER_MIN)
    const tooltip = [program.title, timeRange(startMs, stopMs), program.category, program.desc]
      .filter(Boolean)
      .join('\n')

    return { title: program.title, tooltip, leftPx, widthPx, startMs, stopMs }
  }

  function timeRange(startMs: number, stopMs: number): string {
    const fmt = (ms: number) =>
      new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    return `${fmt(startMs)} – ${fmt(stopMs)}`
  }

  function floorToHour(date: Date): Date {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours())
  }

  function ceilToHour(date: Date): Date {
    const floored = floorToHour(date)
    return floored.getTime() === date.getTime()
      ? floored
      : new Date(floored.getTime() + 60 * 60 * 1000)
  }

  const nowTimer = setInterval(() => (now = Date.now()), 60_000)
  onDestroy(() => clearInterval(nowTimer))
</script>

<div
  class="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700"
>
  <p class="text-xs text-gray-500 dark:text-gray-400">Times shown in your local timezone.</p>
  <button
    type="button"
    class="btn-secondary h-8 px-3"
    disabled={nowLeftPx === null}
    onclick={jumpToNow}
  >
    Now
  </button>
</div>

<div
  bind:this={scrollEl}
  bind:clientWidth={viewportWidth}
  onscroll={handleScroll}
  class="overflow-auto max-h-[70vh]"
>
  <div class="relative" style="width: {LEFT_COL_WIDTH + totalWidthPx}px">
    <div class="sticky top-0 z-20 flex bg-white dark:bg-primary-810">
      <div
        class="sticky left-0 z-30 shrink-0 bg-white dark:bg-primary-810 border-r border-b border-gray-200 dark:border-gray-700"
        style="width: {LEFT_COL_WIDTH}px; height: {HEADER_HEIGHT}px"
      ></div>
      <div
        class="relative shrink-0 border-b border-gray-200 dark:border-gray-700"
        style="width: {totalWidthPx}px; height: {HEADER_HEIGHT}px"
      >
        {#each hourTicks as tick (tick.leftPx)}
          <div
            class="absolute top-0 h-full border-l border-gray-100 dark:border-primary-750 pl-1.5 flex flex-col justify-center"
            style="left: {tick.leftPx}px"
          >
            {#if tick.date}
              <span class="text-[11px] text-gray-400 dark:text-gray-500 whitespace-nowrap"
                >{tick.date}</span
              >
            {/if}
            <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap"
              >{tick.time}</span
            >
          </div>
        {/each}
      </div>
    </div>

    {#each rows as { channel, blocks } (channel.key)}
      <div class="flex border-b border-gray-100 dark:border-primary-750">
        <div
          class="sticky left-0 z-10 shrink-0 bg-white dark:bg-primary-810 border-r border-gray-200 dark:border-gray-700 flex items-center gap-2 px-2"
          style="width: {LEFT_COL_WIDTH}px; height: {ROW_HEIGHT}px"
        >
          {#if channel.logo}
            <img src={channel.logo} alt="" class="w-6 h-6 object-contain shrink-0" loading="lazy" />
          {/if}
          <div class="min-w-0">
            <p class="text-sm text-gray-900 dark:text-white truncate" title={channel.name}>
              {channel.name}
            </p>
            {#if channel.number}
              <p class="text-xs text-gray-500 dark:text-gray-400 font-mono">{channel.number}</p>
            {/if}
          </div>
        </div>
        <div class="relative shrink-0" style="width: {totalWidthPx}px; height: {ROW_HEIGHT}px">
          {#each visible(blocks) as block (block.startMs)}
            <div
              class="absolute top-1 bottom-1 rounded-sm bg-gray-100 dark:bg-primary-750 hover:bg-gray-200 dark:hover:bg-primary-700 border border-gray-200 dark:border-gray-700 px-1.5 py-1 overflow-hidden cursor-default"
              style="left: {block.leftPx}px; width: {block.widthPx}px"
              title={block.tooltip}
            >
              <p class="text-xs text-gray-700 dark:text-gray-300 truncate">{block.title}</p>
            </div>
          {/each}
          {#if !blocks.length}
            <p
              class="absolute inset-0 flex items-center px-1.5 text-xs text-gray-400 dark:text-gray-500"
            >
              No programme data
            </p>
          {/if}
        </div>
      </div>
    {/each}

    {#if nowLeftPx !== null}
      <div
        class="absolute top-0 bottom-0 w-px bg-red-500 z-[15] pointer-events-none"
        style="left: {LEFT_COL_WIDTH + nowLeftPx}px"
      ></div>
    {/if}
  </div>
</div>
