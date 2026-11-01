import { useState } from 'react';
import styled from 'styled-components';
import { removeChannel, updateChannel } from '../api/lineups.js';
import type { Channel } from '../types';
import { ChannelFieldsForm } from './ChannelFieldsForm';
import { toChannelRequestBody, type ChannelFieldValues } from './channelFormValues';
import { ChannelMappingForm } from './ChannelMappingForm';
import { MappingStatusBadge } from './MappingStatusBadge';
import { StatusBadge } from './StatusBadge';
import { Card, DangerButton, ErrorText, FormActions, SecondaryButton } from '../styles/primitives';

const Row = styled(Card)`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
`;

const NameBlock = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const Name = styled.span`
  font-size: 16px;
  font-weight: 600;
`;

const Meta = styled.span`
  font-size: 13px;
  color: #666;
  font-family: ui-monospace, monospace;
`;

const MappingSummary = styled.span`
  font-size: 13px;
  color: #666;
`;

type Mode = 'view' | 'edit' | 'mapping';

interface ChannelRowProps {
  lineupId: string;
  channel: Channel;
  sdLineupIds: string[];
  onChanged: (channel: Channel) => void;
  onRemoved: (channelId: string) => void;
}

/**
 * A single channel's display row: metadata, edit/delete actions, mapping
 * status, and the inline mapping-confirmation form.
 */
export function ChannelRow({ lineupId, channel, sdLineupIds, onChanged, onRemoved }: ChannelRowProps) {
  const [mode, setMode] = useState<Mode>('view');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleEditSubmit(values: ChannelFieldValues) {
    const updated = (await updateChannel(
      lineupId,
      channel.id,
      toChannelRequestBody(values),
    )) as Channel;
    onChanged(updated);
    setMode('view');
  }

  async function handleDelete() {
    if (!window.confirm(`Remove channel "${channel.name}"? This cannot be undone.`)) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await removeChannel(lineupId, channel.id);
      onRemoved(channel.id);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  }

  return (
    <Row>
      <Header>
        <NameBlock>
          <Name>
            {channel.number ? `${channel.number} - ` : ''}
            {channel.name}
          </Name>
          <Meta>
            {channel.tvgId && <>tvg-id: {channel.tvgId} </>}
            {channel.group && <>· group: {channel.group} </>}
            {channel.logoUrl && <>· logo: {channel.logoUrl} </>}
            {channel.sourceStreamUrl && <>· stream: {channel.sourceStreamUrl}</>}
          </Meta>
          {channel.missingSince && (
            <StatusBadge $tone="warning">Missing since {channel.missingSince}</StatusBadge>
          )}
        </NameBlock>
        <FormActions>
          <MappingStatusBadge mapping={channel.mapping} />
          <SecondaryButton
            type="button"
            onClick={() => setMode(mode === 'mapping' ? 'view' : 'mapping')}
          >
            {mode === 'mapping' ? 'Close' : 'Set mapping'}
          </SecondaryButton>
          <SecondaryButton type="button" onClick={() => setMode(mode === 'edit' ? 'view' : 'edit')}>
            {mode === 'edit' ? 'Close' : 'Edit'}
          </SecondaryButton>
          <DangerButton type="button" disabled={deleting} onClick={handleDelete}>
            {deleting ? 'Removing...' : 'Remove'}
          </DangerButton>
        </FormActions>
      </Header>

      {channel.mapping?.sdStationId && (
        <MappingSummary>
          Mapped to station {channel.mapping.sdStationId} in lineup {channel.mapping.sdLineupId}
          {channel.mapping.confirmedAt ? ` (confirmed ${channel.mapping.confirmedAt})` : ''}
        </MappingSummary>
      )}

      {deleteError && <ErrorText>{deleteError}</ErrorText>}

      {mode === 'edit' && (
        <ChannelFieldsForm
          initialValues={{
            name: channel.name,
            number: channel.number ?? '',
            logoUrl: channel.logoUrl ?? '',
            tvgId: channel.tvgId ?? '',
            sourceStreamUrl: channel.sourceStreamUrl ?? '',
          }}
          submitLabel="Save changes"
          onSubmit={handleEditSubmit}
          onCancel={() => setMode('view')}
        />
      )}

      {mode === 'mapping' && (
        <ChannelMappingForm
          lineupId={lineupId}
          channel={channel}
          sdLineupIds={sdLineupIds}
          onSaved={(updated) => {
            onChanged(updated);
            setMode('view');
          }}
          onCancel={() => setMode('view')}
        />
      )}
    </Row>
  );
}
