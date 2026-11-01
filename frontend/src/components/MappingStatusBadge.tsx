import type { ChannelMapping } from '../types';
import { StatusBadge, type StatusTone } from './StatusBadge';

interface MappingStatusBadgeProps {
  mapping: ChannelMapping | null;
}

/**
 * Renders a channel's mapping state - unmapped / pending confirmation /
 * confirmed - using the shared StatusBadge component. There's no
 * suggestion-scoring UI yet (Phase 3), so "pending" here just means a
 * mapping was set directly but not marked confirmed.
 */
export function MappingStatusBadge({ mapping }: MappingStatusBadgeProps) {
  const { tone, label } = describeMapping(mapping);
  return <StatusBadge $tone={tone}>{label}</StatusBadge>;
}

function describeMapping(mapping: ChannelMapping | null): { tone: StatusTone; label: string } {
  if (!mapping || !mapping.sdStationId) {
    return { tone: 'pending', label: 'Unmapped' };
  }
  if (!mapping.confirmed) {
    return { tone: 'warning', label: 'Pending confirmation' };
  }
  return { tone: 'ok', label: 'Confirmed' };
}
