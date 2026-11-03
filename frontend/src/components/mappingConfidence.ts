import type { StatusTone } from './StatusBadge';

/**
 * Mirrors the backend's bulk-accept cutoff so suggestion/search-result
 * confidence tones look consistent with what bulk-accept would actually
 * do. Shared by `ChannelSuggestions` (per-channel suggestion review) and
 * `ChannelMappingForm` (the station search-and-select picker, backlog item
 * 37) - kept in its own plain module, rather than exported from one of
 * those component files, so both stay Fast-Refresh-friendly (a component
 * file exporting a non-component value breaks that).
 *
 * Known limitation: this is a hand-maintained copy, not a value fetched
 * from the backend. `BulkAcceptResult.threshold` (see `types/index.ts`)
 * only comes back from the bulk-accept-suggestions response, and neither
 * caller here has a threshold to read before that endpoint has ever run.
 * If `backend/app/services/suggestions.py`'s `BULK_ACCEPT_THRESHOLD` is
 * retuned, update this constant to match.
 */
export const BULK_ACCEPT_THRESHOLD_DISPLAY = 0.92;

/** Reuses `StatusBadge`'s tone system rather than inventing a new one. */
export function confidenceTone(score: number): StatusTone {
  if (score >= BULK_ACCEPT_THRESHOLD_DISPLAY) {
    return 'ok';
  }
  if (score >= 0.6) {
    return 'warning';
  }
  return 'pending';
}
