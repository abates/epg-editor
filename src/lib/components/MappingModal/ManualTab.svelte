<script lang="ts">
  import type { DatabaseChannelData } from '$lib/types/database'
  import type { GuideEntryField, GuideEntryInput } from '$lib/core/mappingValidation'
  import { DATABASE_URL, EPG_CHANNEL_REQUEST_URL } from '$lib/constants'
  import { searchDatabase } from '$lib/api'

  interface Props {
    sites: string[]
    initial: GuideEntryInput
    errors: Partial<Record<GuideEntryField, string>>
    saving: boolean
    onSubmit: (entry: GuideEntryInput) => void
  }

  let { sites, initial, errors, saving, onSubmit }: Props = $props()

  // svelte-ignore state_referenced_locally
  let entry: GuideEntryInput = $state({ ...initial, lang: initial.lang ?? '' })

  // xmltv_id search-as-you-type: pick a channel, then one of its feeds, like epg's
  // channels:edit command [FR-E-1]
  let channels: DatabaseChannelData[] = $state([])
  let picked: DatabaseChannelData | null = $state(null)
  let lookupError: string | null = $state(null)
  let showResults = $state(false)

  let latest = 0
  $effect(() => {
    const query = entry.xmltv_id.trim()
    const id = ++latest
    if (query.length < 2 || !showResults) {
      channels = []
      return
    }
    const timer = setTimeout(async () => {
      try {
        const result = await searchDatabase(query)
        if (id === latest) {
          channels = result
          lookupError = null
        }
      } catch (cause) {
        if (id === latest) lookupError = (cause as Error).message
      }
    }, 200)

    return () => clearTimeout(timer)
  })

  function pickChannel(channel: DatabaseChannelData) {
    picked = channel
    showResults = false
    entry.xmltv_id = channel.feeds.find(feed => feed.is_main)?.xmltv_id ?? channel.xmltv_id
  }
</script>

<!-- FR-E-1..3 -->
<form
  class="flex flex-col gap-4"
  onsubmit={event => {
    event.preventDefault()
    onSubmit({ ...entry, lang: entry.lang || null })
  }}
>
  <div class="grid gap-4 sm:grid-cols-2">
    <div>
      <label for="manual-site" class="field-label">Site</label>
      <input
        id="manual-site"
        class="field font-mono"
        list="manual-sites"
        bind:value={entry.site}
        placeholder="tvtv.us"
        required
      />
      <datalist id="manual-sites">
        {#each sites as site (site)}
          <option value={site}></option>
        {/each}
      </datalist>
      {#if errors.site}<p class="field-error">{errors.site}</p>{/if}
    </div>
    <div>
      <label for="manual-site-id" class="field-label">Site ID</label>
      <input id="manual-site-id" class="field font-mono" bind:value={entry.site_id} required />
      {#if errors.site_id}<p class="field-error">{errors.site_id}</p>{/if}
    </div>
    <div>
      <label for="manual-lang" class="field-label">Language</label>
      <input
        id="manual-lang"
        class="field font-mono"
        bind:value={entry.lang}
        placeholder="en"
        maxlength="2"
      />
      {#if errors.lang}<p class="field-error">{errors.lang}</p>{/if}
    </div>
    <div class="relative">
      <label for="manual-xmltv-id" class="field-label">xmltv_id</label>
      <input
        id="manual-xmltv-id"
        class="field font-mono"
        bind:value={entry.xmltv_id}
        placeholder="WCBSTV.us@SD"
        autocomplete="off"
        oninput={() => {
          showResults = true
          picked = null
        }}
      />
      {#if errors.xmltv_id}<p class="field-error">{errors.xmltv_id}</p>{/if}
      {#if lookupError}<p class="field-hint">{lookupError}</p>{/if}
      {#if showResults && channels.length}
        <ul
          class="absolute z-10 mt-1 w-full max-h-64 overflow-y-auto rounded-md border border-gray-200 dark:border-primary-700 bg-white dark:bg-primary-810 shadow-lg"
        >
          {#each channels as channel (channel.xmltv_id)}
            <li>
              <button
                type="button"
                class="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-primary-750 cursor-pointer"
                onclick={() => pickChannel(channel)}
              >
                <div class="text-sm text-gray-900 dark:text-white">
                  {channel.name}
                  {#if channel.closed}<span class="text-xs text-red-600">(closed)</span>{/if}
                </div>
                <div class="text-xs font-mono text-gray-500 dark:text-gray-400">
                  {channel.xmltv_id}
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>

  {#if picked && picked.feeds.length}
    <!-- A select, not chips: national networks have hundreds of local feeds -->
    <div>
      <label for="manual-feed" class="field-label">Feed of {picked.name}</label>
      <select id="manual-feed" class="field font-mono" bind:value={entry.xmltv_id}>
        <option value={picked.xmltv_id}>{picked.xmltv_id} (no feed)</option>
        {#each picked.feeds as feed (feed.xmltv_id)}
          <option value={feed.xmltv_id}>
            {feed.xmltv_id}{feed.is_main ? ' (main)' : ''}{feed.name ? ` · ${feed.name}` : ''}
          </option>
        {/each}
      </select>
    </div>
  {/if}

  <p class="text-xs text-gray-500 dark:text-gray-400">
    Channel missing? Request it from
    <a class="underline" href={EPG_CHANNEL_REQUEST_URL} target="_blank" rel="noreferrer">
      iptv-org/epg
    </a>
    or add it to
    <a class="underline" href={DATABASE_URL} target="_blank" rel="noreferrer">iptv-org/database</a>.
  </p>

  <div class="flex justify-end">
    <button type="submit" class="btn-primary" disabled={saving}>Save manual entry</button>
  </div>
</form>
