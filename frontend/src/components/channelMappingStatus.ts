import type { ChannelMapping } from '../types';

/**
 * Whether a channel's mapping counts as "mapped" - both `sdStationId` and
 * `sdLineupId` set (not just `sdStationId`), matching the backend's own
 * definition (`services/xmltv.py`'s `mapped_channels()` and the orphan-
 * removal guard in `services/lineups.py`). No real code path currently
 * produces a channel with `sdStationId` set but `sdLineupId` null, but this
 * keeps the frontend and backend from silently disagreeing on what counts
 * as mapped if that ever changes (backlog item 38 follow-up).
 *
 * Kept in its own plain module, rather than exported from one of its
 * caller component files, so those stay Fast-Refresh-friendly (a component
 * file exporting a non-component value breaks that) - mirrors
 * `mappingConfidence.ts`'s rationale.
 */
export function isChannelMapped(mapping: ChannelMapping | null): boolean {
  return Boolean(mapping?.sdStationId && mapping?.sdLineupId);
}
