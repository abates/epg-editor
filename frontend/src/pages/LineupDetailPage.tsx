import { useCallback, useEffect, useState } from 'react';
import styled from 'styled-components';
import { addChannel, deleteLineup, getLineup } from '../api/lineups.js';
import { ChannelFieldsForm } from '../components/ChannelFieldsForm';
import {
  emptyChannelFieldValues,
  toChannelRequestBody,
  type ChannelFieldValues,
} from '../components/channelFormValues';
import { ChannelRow } from '../components/ChannelRow';
import { ReimportM3uPanel } from '../components/ReimportM3uPanel';
import { SdLineupIdsEditor } from '../components/SdLineupIdsEditor';
import { SuggestionsPanel } from '../components/SuggestionsPanel';
import { SyncAndGeneratePanel } from '../components/SyncAndGeneratePanel';
import type { Channel, Lineup } from '../types';
import {
  Card,
  DangerButton,
  ErrorText,
  Page,
  SecondaryButton,
  SectionTitle,
  SubsectionTitle,
} from '../styles/primitives';

const BackRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
`;

const Meta = styled.p`
  color: #666;
  font-size: 14px;
  margin: 0 0 24px;
`;

const ChannelList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
`;

type LoadState =
  | { status: 'loading' }
  | { status: 'ok'; lineup: Lineup }
  | { status: 'error'; message: string };

interface LineupDetailPageProps {
  lineupId: string;
  onBack: () => void;
}

/**
 * Detail view for a single lineup: its SD lineup associations, mapping
 * suggestion generation/bulk-accept (`SuggestionsPanel`), channel list
 * (with per-channel edit/delete/mapping actions and, via `ChannelRow`,
 * per-channel suggestion accept/reject), a form to add a channel manually,
 * and - for `m3u`-sourced lineups only - a re-import control
 * (`ReimportM3uPanel`).
 */
export function LineupDetailPage({ lineupId, onBack }: LineupDetailPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Fetches the lineup and lands it (or any failure) into state, without
  // touching `state` synchronously first - the mount effect below relies
  // on the initial `useState` value for the loading state instead of
  // setting it again itself.
  const load = useCallback(() => {
    (getLineup(lineupId) as Promise<Lineup>)
      .then((lineup) => setState({ status: 'ok', lineup }))
      .catch((error: unknown) =>
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        }),
      );
  }, [lineupId]);

  useEffect(() => {
    load();
  }, [load]);

  function handleChannelChanged(updated: Channel) {
    setState((prev) => {
      if (prev.status !== 'ok') {
        return prev;
      }
      return {
        status: 'ok',
        lineup: {
          ...prev.lineup,
          channels: prev.lineup.channels.map((channel) =>
            channel.id === updated.id ? updated : channel,
          ),
        },
      };
    });
  }

  function handleChannelRemoved(channelId: string) {
    setState((prev) => {
      if (prev.status !== 'ok') {
        return prev;
      }
      return {
        status: 'ok',
        lineup: {
          ...prev.lineup,
          channels: prev.lineup.channels.filter((channel) => channel.id !== channelId),
        },
      };
    });
  }

  function handleSdLineupIdsChanged(sdLineupIds: string[]) {
    setState((prev) => {
      if (prev.status !== 'ok') {
        return prev;
      }
      return { status: 'ok', lineup: { ...prev.lineup, sdLineupIds } };
    });
  }

  function handleReimported(lineup: Lineup) {
    // The response already reflects the fully-merged, persisted lineup
    // (added/updated/flagged-missing channels all included) - replace the
    // whole lineup wholesale rather than trying to reconcile it field by
    // field against the previous state.
    setState({ status: 'ok', lineup });
  }

  function handleLineupRefreshed(lineup: Lineup) {
    // Same rationale as `handleReimported`: `SuggestionsPanel` re-fetches
    // the whole lineup itself after generate/bulk-accept (neither
    // endpoint's response includes the per-channel suggestions/mappings it
    // changed), so replace wholesale rather than merging.
    setState({ status: 'ok', lineup });
  }

  async function handleDeleteLineup() {
    if (state.status !== 'ok') {
      return;
    }
    const { lineup } = state;
    const channelCount = lineup.channels.length;
    const confirmed = window.confirm(
      `Delete lineup "${lineup.name}"? This will permanently remove it and all ${channelCount} ` +
        `channel${channelCount === 1 ? '' : 's'} in it, including any confirmed mappings. ` +
        'This cannot be undone.',
    );
    if (!confirmed) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteLineup(lineupId);
      onBack();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : String(err));
      setDeleting(false);
    }
  }

  async function handleAddChannel(values: ChannelFieldValues) {
    const created = (await addChannel(lineupId, toChannelRequestBody(values))) as Channel;
    setState((prev) => {
      if (prev.status !== 'ok') {
        return prev;
      }
      return { status: 'ok', lineup: { ...prev.lineup, channels: [...prev.lineup.channels, created] } };
    });
  }

  return (
    <Page>
      <BackRow>
        <SecondaryButton type="button" onClick={onBack}>
          &larr; Back to lineups
        </SecondaryButton>
        {state.status === 'ok' && (
          <DangerButton type="button" disabled={deleting} onClick={handleDeleteLineup}>
            {deleting ? 'Deleting...' : 'Delete lineup'}
          </DangerButton>
        )}
      </BackRow>

      {state.status === 'loading' && <p>Loading lineup...</p>}
      {state.status === 'error' && (
        <ErrorText>Failed to load lineup: {state.message}</ErrorText>
      )}
      {deleteError && <ErrorText>{deleteError}</ErrorText>}

      {state.status === 'ok' && (
        <>
          <SectionTitle>{state.lineup.name}</SectionTitle>
          <Meta>
            Source: {state.lineup.source} · {state.lineup.channels.length} channel
            {state.lineup.channels.length === 1 ? '' : 's'} · created {state.lineup.createdAt}
          </Meta>

          <SubsectionTitle>Sync & Generate</SubsectionTitle>
          <SyncAndGeneratePanel lineupId={lineupId} />

          {state.lineup.source === 'm3u' && (
            <>
              <SubsectionTitle>Re-import M3U</SubsectionTitle>
              <ReimportM3uPanel
                lineupId={lineupId}
                onImported={handleReimported}
                onChannelRemoved={handleChannelRemoved}
              />
            </>
          )}

          <SubsectionTitle>SchedulesDirect lineups</SubsectionTitle>
          <SdLineupIdsEditor
            lineupId={lineupId}
            sdLineupIds={state.lineup.sdLineupIds}
            onChanged={handleSdLineupIdsChanged}
          />

          <SubsectionTitle>Mapping suggestions</SubsectionTitle>
          <SuggestionsPanel
            lineupId={lineupId}
            channels={state.lineup.channels}
            onRefreshed={handleLineupRefreshed}
          />

          <SubsectionTitle>Channels</SubsectionTitle>
          {state.lineup.channels.length === 0 ? (
            <p>No channels yet - add one below.</p>
          ) : (
            <ChannelList>
              {state.lineup.channels.map((channel) => (
                <ChannelRow
                  key={channel.id}
                  lineupId={lineupId}
                  channel={channel}
                  sdLineupIds={state.lineup.sdLineupIds}
                  onChanged={handleChannelChanged}
                  onRemoved={handleChannelRemoved}
                />
              ))}
            </ChannelList>
          )}

          <SubsectionTitle>Add a channel</SubsectionTitle>
          <Card>
            <ChannelFieldsForm
              initialValues={emptyChannelFieldValues}
              submitLabel="Add channel"
              onSubmit={handleAddChannel}
            />
          </Card>
        </>
      )}
    </Page>
  );
}
