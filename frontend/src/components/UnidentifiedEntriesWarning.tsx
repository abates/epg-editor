import styled from 'styled-components';
import { Card } from '../styles/primitives';

// Same amber warning tone used elsewhere for partial-failure/non-fatal
// notices (see `RefreshNowPanel`'s `WarningCard` and `StatusBadge`'s
// `warning` tone) - reused here rather than inventing a new visual style.
const WarningCard = styled(Card)`
  margin: 12px 0;
  background: #fdf6e3;
  border-color: #e3c97e;
  color: #7a5a00;
  font-size: 13px;
`;

interface UnidentifiedEntriesWarningProps {
  unidentifiedEntryCount: number;
}

/**
 * Warns that `unidentifiedEntryCount` parsed M3U entries had no `tvg-id` or
 * channel number, so they'll always be treated as new on every import (risk
 * of duplicate channels accumulating on repeated re-imports). Renders
 * nothing when the count is 0.
 *
 * Shared between the initial M3U import flow (`LineupsListPage`) and the
 * re-import flow (`M3UImportResultPanel`) so both surface the same warning
 * from `M3UImportResult.unidentifiedEntryCount` - the first import is
 * actually the most useful time to see it, before any re-imports have had a
 * chance to accumulate duplicates.
 */
export function UnidentifiedEntriesWarning({
  unidentifiedEntryCount,
}: UnidentifiedEntriesWarningProps) {
  if (unidentifiedEntryCount <= 0) {
    return null;
  }

  return (
    <WarningCard>
      {unidentifiedEntryCount} channel
      {unidentifiedEntryCount === 1 ? ' ' : 's '}
      in this file {unidentifiedEntryCount === 1 ? 'has' : 'have'} no tvg-id
      or channel number and will always be treated as new on every import -
      this can cause duplicate channels to accumulate if you re-import this
      file repeatedly.
    </WarningCard>
  );
}
