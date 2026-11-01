import { useState } from 'react';
import styled from 'styled-components';
import { removeChannel } from '../api/lineups.js';
import type { Channel, M3UImportResult } from '../types';
import { DangerButton, ErrorText } from '../styles/primitives';
import { UnidentifiedEntriesWarning } from './UnidentifiedEntriesWarning';

const Summary = styled.p`
  margin: 0 0 8px;
  font-size: 14px;
`;

const Section = styled.div`
  margin-top: 12px;
`;

const SectionTitle = styled.h3`
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 6px;
  color: #444;
`;

const ChannelList = styled.ul`
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const ChannelItem = styled.li`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 13px;
`;

interface M3UImportResultPanelProps {
  lineupId: string;
  result: M3UImportResult;
  onChannelRemoved: (channelId: string) => void;
}

/**
 * Shows the Added / Updated / Flagged missing breakdown from an M3U
 * (re-)import, with a "Remove" action (behind the same confirm-dialog
 * pattern as `ChannelRow`) for each flagged-missing channel so the user can
 * confirm deletion of a channel the backend intentionally did *not* delete
 * on its own.
 *
 * Removed channels are tracked locally (`removedIds`) so a channel that's
 * just been removed disappears from this one-time result display too,
 * without needing the caller to re-derive a new `result` object.
 */
export function M3UImportResultPanel({
  lineupId,
  result,
  onChannelRemoved,
}: M3UImportResultPanelProps) {
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());
  const [removeError, setRemoveError] = useState<string | null>(null);

  async function handleRemove(channel: Channel) {
    if (!window.confirm(`Remove channel "${channel.name}"? This cannot be undone.`)) {
      return;
    }
    setRemovingId(channel.id);
    setRemoveError(null);
    try {
      await removeChannel(lineupId, channel.id);
      setRemovedIds((prev) => new Set(prev).add(channel.id));
      onChannelRemoved(channel.id);
    } catch (err) {
      setRemoveError(err instanceof Error ? err.message : String(err));
    } finally {
      setRemovingId(null);
    }
  }

  const added = result.added;
  const updated = result.updated;
  const flaggedMissing = result.flaggedMissing.filter((channel) => !removedIds.has(channel.id));

  return (
    <div>
      <Summary>
        Added {added.length} channel{added.length === 1 ? '' : 's'}, updated {updated.length}{' '}
        channel{updated.length === 1 ? '' : 's'}, flagged {flaggedMissing.length} channel
        {flaggedMissing.length === 1 ? '' : 's'} as missing.
      </Summary>

      <UnidentifiedEntriesWarning
        unidentifiedEntryCount={result.unidentifiedEntryCount}
      />

      {added.length > 0 && (
        <Section>
          <SectionTitle>Added</SectionTitle>
          <ChannelList>
            {added.map((channel) => (
              <ChannelItem key={channel.id}>
                <span>{describeChannel(channel)}</span>
              </ChannelItem>
            ))}
          </ChannelList>
        </Section>
      )}

      {updated.length > 0 && (
        <Section>
          <SectionTitle>Updated</SectionTitle>
          <ChannelList>
            {updated.map((channel) => (
              <ChannelItem key={channel.id}>
                <span>{describeChannel(channel)}</span>
              </ChannelItem>
            ))}
          </ChannelList>
        </Section>
      )}

      {flaggedMissing.length > 0 && (
        <Section>
          <SectionTitle>Flagged missing</SectionTitle>
          <ChannelList>
            {flaggedMissing.map((channel) => (
              <ChannelItem key={channel.id}>
                <span>{describeChannel(channel)}</span>
                <DangerButton
                  type="button"
                  disabled={removingId === channel.id}
                  onClick={() => handleRemove(channel)}
                >
                  {removingId === channel.id ? 'Removing...' : 'Remove'}
                </DangerButton>
              </ChannelItem>
            ))}
          </ChannelList>
        </Section>
      )}

      {removeError && <ErrorText>{removeError}</ErrorText>}
    </div>
  );
}

function describeChannel(channel: Channel): string {
  const prefix = channel.number ? `${channel.number} - ` : '';
  const suffix = channel.group ? ` (${channel.group})` : '';
  return `${prefix}${channel.name}${suffix}`;
}
