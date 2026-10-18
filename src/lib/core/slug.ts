import slugify from 'slugify'

// NFR-SEC-3: slugs are used in paths, so they must match this before any filesystem access
export const SLUG_PATTERN = /^[a-z0-9][a-z0-9.-]*$/

export function isValidSlug(slug: string): boolean {
  return SLUG_PATTERN.test(slug)
}

export function toSlug(name: string): string {
  return slugify(name, { lower: true, strict: true, trim: true })
}
