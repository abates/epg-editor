<script lang="ts">
  interface Props {
    sourceType?: string
    url?: string
  }

  let { sourceType = $bindable('upload'), url = '' }: Props = $props()
</script>

<!-- FR-M-1 / FR-M-2: file upload or a URL the server fetches -->
<fieldset class="flex flex-col gap-3">
  <legend class="field-label">M3U playlist</legend>
  <div class="flex gap-4 text-sm text-gray-700 dark:text-gray-300">
    <label class="inline-flex items-center gap-2 cursor-pointer">
      <input type="radio" name="sourceType" value="upload" bind:group={sourceType} />
      Upload a file
    </label>
    <label class="inline-flex items-center gap-2 cursor-pointer">
      <input type="radio" name="sourceType" value="url" bind:group={sourceType} />
      Fetch from a URL
    </label>
  </div>

  {#if sourceType === 'upload'}
    <div>
      <input
        type="file"
        name="file"
        accept=".m3u,.m3u8,audio/x-mpegurl,application/vnd.apple.mpegurl"
        aria-label="M3U file"
        class="block w-full text-sm text-gray-500 dark:text-gray-400 file:mr-3 file:h-9 file:px-3 file:rounded-md file:border file:border-gray-200 file:bg-white file:text-sm file:text-gray-700 file:cursor-pointer dark:file:border-primary-700 dark:file:bg-primary-750 dark:file:text-gray-200"
        required
      />
      <p class="field-hint">.m3u or .m3u8, up to 5 MB.</p>
    </div>
  {:else}
    <div>
      <input
        type="url"
        name="url"
        value={url}
        placeholder="http://192.168.1.10/lineup.m3u"
        aria-label="Playlist URL"
        class="field font-mono"
        required
      />
      <p class="field-hint">
        For an HDHomeRun this is <span class="font-mono">http://&lt;device-ip&gt;/lineup.m3u</span>.
        The URL is saved so the lineup can be refreshed later.
      </p>
    </div>
  {/if}
</fieldset>
