<script lang="ts">
  import { Alert, ConfirmModal, PlaylistSourceField } from '$lib/components'
  import { MODAL_KEY, type ModalContext } from '$lib/modal.svelte'
  import { toast } from '@zerodevx/svelte-toast'
  import { enhance } from '$app/forms'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import { getContext } from 'svelte'
  import type { SubmitFunction } from '@sveltejs/kit'
  import type { PageProps } from './$types'

  let { data, form }: PageProps = $props()

  const modal = getContext<ModalContext>(MODAL_KEY)
  const lineup = $derived(data.lineup)
  const defaults = $derived(data.grabDefaults)

  // Submitted values after a failed save, otherwise the stored settings
  const failed = $derived(form?.action === 'save' ? form.values : undefined)
  const field = (name: string, stored: string | number | undefined) =>
    failed?.[name] ?? (stored === undefined ? '' : String(stored))

  let sourceType = $state('upload')
  let deleteForm: HTMLFormElement | undefined = $state()
  let busy: string | null = $state(null)

  function confirmDelete() {
    modal.open(ConfirmModal, {
      title: `Delete ${lineup.name}?`,
      message:
        'This removes the lineup, its mappings, its channels.xml and its guide files. It cannot be undone.',
      confirmLabel: 'Delete lineup',
      onConfirm: () => deleteForm?.requestSubmit()
    })
  }

  // Keeps the form values after saving and shows the result as a toast
  function submit(name: string): SubmitFunction {
    return () => {
      busy = name
      return async ({ update, result }) => {
        await update({ reset: false })
        busy = null
        if (result.type === 'success' && name === 'save') toast.push('Settings saved')
      }
    }
  }
</script>

<svelte:head>
  <title>Settings · {lineup.name} · epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-3xl flex flex-col gap-4">
  <a
    href={resolve('/lineups/[slug]', { slug: lineup.slug })}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} />
    {lineup.name}
  </a>
  <h1 class="text-xl text-gray-900 dark:text-white font-medium">Settings</h1>

  <form
    method="POST"
    action="?/save"
    class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 sm:p-6 flex flex-col gap-5"
    use:enhance={submit('save')}
  >
    {#if form?.action === 'save' && form.error}
      <Alert variant="error">{form.error}</Alert>
    {/if}

    <div class="grid gap-5 sm:grid-cols-2">
      <div>
        <label for="name" class="field-label">Name</label>
        <input id="name" name="name" class="field" value={field('name', lineup.name)} required />
      </div>
      <div>
        <span class="field-label">Slug</span>
        <p class="h-10 flex items-center font-mono text-sm text-gray-500 dark:text-gray-400">
          {lineup.slug}
        </p>
      </div>
    </div>

    <!-- FR-L-4 -->
    <fieldset class="flex flex-col gap-4">
      <legend class="text-gray-900 dark:text-white font-medium mb-2">Suggestions</legend>
      <div class="grid gap-5 sm:grid-cols-2">
        <div>
          <label for="countries" class="field-label">Countries</label>
          <input
            id="countries"
            name="countries"
            class="field font-mono"
            value={field('countries', lineup.filters.countries.join(', '))}
          />
        </div>
        <div>
          <label for="languages" class="field-label">Languages</label>
          <input
            id="languages"
            name="languages"
            class="field font-mono"
            placeholder="any"
            value={field('languages', lineup.filters.languages.join(', '))}
          />
        </div>
      </div>
      <div>
        <label for="preferredSites" class="field-label">Preferred sites</label>
        <input
          id="preferredSites"
          name="preferredSites"
          class="field font-mono"
          list="known-sites"
          value={field('preferredSites', lineup.filters.preferredSites.join(', '))}
        />
        <p class="field-hint">Comma separated, most preferred first.</p>
        <datalist id="known-sites">
          {#each data.sites as site (site)}
            <option value={site}></option>
          {/each}
        </datalist>
      </div>
    </fieldset>

    <!-- FR-L-5: blank fields use the server defaults -->
    <fieldset class="flex flex-col gap-4">
      <legend class="text-gray-900 dark:text-white font-medium mb-2">Grabbing</legend>
      <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          name="enabled"
          checked={failed ? failed.enabled === 'on' : lineup.grab.enabled}
        />
        Include in scheduled grabs
      </label>
      <div class="grid gap-5 grid-cols-2 sm:grid-cols-3">
        <div>
          <label for="days" class="field-label">Days</label>
          <input
            id="days"
            name="days"
            inputmode="numeric"
            class="field"
            placeholder={defaults.days === null ? 'site default' : String(defaults.days)}
            value={field('days', lineup.grab.days)}
          />
        </div>
        <div>
          <label for="maxConnections" class="field-label">Max connections</label>
          <input
            id="maxConnections"
            name="maxConnections"
            inputmode="numeric"
            class="field"
            placeholder={String(defaults.maxConnections)}
            value={field('maxConnections', lineup.grab.maxConnections)}
          />
        </div>
        <div>
          <label for="delay" class="field-label">Delay (ms)</label>
          <input
            id="delay"
            name="delay"
            inputmode="numeric"
            class="field"
            placeholder={String(defaults.delay)}
            value={field('delay', lineup.grab.delay)}
          />
        </div>
        <div>
          <label for="timeout" class="field-label">Timeout (ms)</label>
          <input
            id="timeout"
            name="timeout"
            inputmode="numeric"
            class="field"
            placeholder={String(defaults.timeout)}
            value={field('timeout', lineup.grab.timeout)}
          />
        </div>
        <div>
          <label for="gzip" class="field-label">Gzip copy</label>
          <select
            id="gzip"
            name="gzip"
            class="field"
            value={field(
              'gzip',
              lineup.grab.gzip === undefined ? '' : lineup.grab.gzip ? 'on' : 'off'
            )}
          >
            <option value="">Default ({defaults.gzip ? 'on' : 'off'})</option>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </div>
      </div>
    </fieldset>

    <div class="flex justify-end">
      <button type="submit" class="btn-primary" disabled={busy !== null}>
        {#if busy === 'save'}<Icon.Spinner size={16} />{/if}
        Save settings
      </button>
    </div>
  </form>

  <!-- FR-M-1 / FR-M-2 / FR-M-6 -->
  <div
    class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 sm:p-6 flex flex-col gap-4"
  >
    <h2 class="text-gray-900 dark:text-white font-medium">Playlist</h2>
    <p class="text-sm text-gray-500 dark:text-gray-400">
      {#if lineup.source.type === 'url'}
        Fetched from <span class="font-mono break-all">{lineup.source.url}</span>
      {:else}
        Uploaded
      {/if}
      on {new Date(lineup.source.importedAt).toLocaleString()}. Replacing it shows the changes
      first; mappings of unchanged channels are kept.
    </p>
    {#if form?.action === 'source' && form.error}
      <Alert variant="error">{form.error}</Alert>
    {/if}

    {#if lineup.source.type === 'url'}
      <form method="POST" action="?/source" use:enhance={submit('refresh')}>
        <input type="hidden" name="refresh" value="true" />
        <button type="submit" class="btn-secondary" disabled={busy !== null}>
          {#if busy === 'refresh'}<Icon.Spinner size={16} />{/if}
          Refresh from URL
        </button>
      </form>
    {/if}

    <form
      method="POST"
      action="?/source"
      enctype="multipart/form-data"
      class="flex flex-col gap-4 border-t border-gray-200 dark:border-gray-700 pt-4"
      use:enhance={submit('source')}
    >
      <PlaylistSourceField bind:sourceType url={lineup.source.url} />
      <div class="flex justify-end">
        <button type="submit" class="btn-secondary" disabled={busy !== null}>
          {#if busy === 'source'}<Icon.Spinner size={16} />{/if}
          Replace playlist
        </button>
      </div>
    </form>
  </div>

  <!-- FR-L-3 -->
  <div
    class="rounded-md bg-white dark:bg-primary-810 border border-red-200 dark:border-red-900 p-4 sm:p-6 flex flex-wrap items-center justify-between gap-3"
  >
    <div>
      <h2 class="text-gray-900 dark:text-white font-medium">Delete lineup</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        Removes its mappings, channels.xml and guide files.
      </p>
    </div>
    <form method="POST" action="?/delete" bind:this={deleteForm} use:enhance>
      <button type="button" class="btn-danger" onclick={confirmDelete}>Delete lineup</button>
    </form>
  </div>
</div>
