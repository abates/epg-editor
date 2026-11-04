import type { ChannelMapping } from '../types';
import { isChannelMapped } from './channelMappingStatus';
import { StatusBadge, type StatusTone } from './StatusBadge';

interface MappingStatusBadgeProps {
  mapping: ChannelMapping | null;
}

/**
 * Renders a channel's mapping state - unmapped / mapped - using the shared
 * StatusBadge component. "Mapped" is derived from `sdStationId`/
 * `sdLineupId` both being set (see `isChannelMapped`); there's no separate
 * confirmed/unconfirmed boolean (backlog item 38) - a station is never set
 * except as the user's final decision.
 */
export function MappingStatusBadge({ mapping }: MappingStatusBadgeProps) {
  const { tone, label } = describeMapping(mapping);
  return <StatusBadge $tone={tone}>{label}</StatusBadge>;
}

function describeMapping(mapping: ChannelMapping | null): { tone: StatusTone; label: string } {
  if (!isChannelMapped(mapping)) {
    return { tone: 'pending', label: 'Unmapped' };
  }
  return { tone: 'ok', label: 'Mapped' };
}
