<script lang="ts">
  import { Alert, PlaylistSourceField } from '$lib/components'
  import { toSlug } from '$lib/core/slug'
  import { enhance } from '$app/forms'
  import { resolve } from '$app/paths'
  import * as Icon from '$lib/icons'
  import type { PageProps } from './$types'

  let { data, form }: PageProps = $props()

  // Starts from the submitted values when the action failed
  const values = $derived(form?.values)
  let name = $state('')
  let slug = $state('')
  let sourceType = $state('upload')
  let submitting = $state(false)

  $effect.pre(() => {
    if (!values) return
    name = values.name
    slug = values.slug
    sourceType = values.sourceType
  })

  const slugPlaceholder = $derived(toSlug(name) || 'living-room')
</script>

<svelte:head>
  <title>New lineup · epg-editor</title>
</svelte:head>

<div class="mx-auto px-3 py-6 w-full max-w-2xl flex flex-col gap-4">
  <a
    href={resolve('/')}
    class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:underline"
  >
    <Icon.ArrowLeft size={14} /> Lineups
  </a>
  <h1 class="text-xl text-gray-900 dark:text-white font-medium">New lineup</h1>

  <form
    method="POST"
    enctype="multipart/form-data"
    class="rounded-md bg-white dark:bg-primary-810 border border-gray-200 dark:border-gray-700 p-4 sm:p-6 flex flex-col gap-5"
    use:enhance={() => {
      submitting = true
      return async ({ update }) => {
        await update({ reset: false })
        submitting = false
      }
    }}
  >
    {#if form?.error}
      <Alert variant="error">{form.error}</Alert>
    {/if}

    <div>
      <label for="name" class="field-label">Name</label>
      <input
        id="name"
        name="name"
        class="field"
        placeholder="Living room HDHomeRun"
        bind:value={name}
        required
      />
    </div>

    <div>
      <label for="slug" class="field-label">Slug</label>
      <input
        id="slug"
        name="slug"
        class="field font-mono"
        placeholder={slugPlaceholder}
        pattern="[a-z0-9][a-z0-9.\-]*"
        bind:value={slug}
      />
      <p class="field-hint">
        Used in the guide URL (<span class="font-mono">/guides/{slug || slugPlaceholder}.xml</span
        >). Leave blank to derive it from the name. It can't be changed later.
      </p>
    </div>

    <PlaylistSourceField bind:sourceType url={values?.url} />

    <div class="grid gap-5 sm:grid-cols-2">
      <div>
        <label for="countries" class="field-label">Countries</label>
        <input
          id="countries"
          name="countries"
          class="field font-mono"
          value={values?.countries ?? 'us'}
        />
        <p class="field-hint">Two-letter codes, comma separated. Used to rank suggestions.</p>
      </div>
      <div>
        <label for="preferredSites" class="field-label">Preferred sites</label>
        <input
          id="preferredSites"
          name="preferredSites"
          class="field font-mono"
          list="known-sites"
          placeholder="tvtv.us"
          value={values?.preferredSites ?? ''}
        />
        <p class="field-hint">Most preferred first. Can be changed in the lineup settings.</p>
      </div>
    </div>
    <datalist id="known-sites">
      {#each data.sites as site (site)}
        <option value={site}></option>
      {/each}
    </datalist>

    <div class="flex justify-end gap-2">
      <a href={resolve('/')} class="btn-secondary">Cancel</a>
      <button type="submit" class="btn-primary" disabled={submitting}>
        {#if submitting}<Icon.Spinner size={16} />{/if}
        Import lineup
      </button>
    </div>
  </form>
</div>
