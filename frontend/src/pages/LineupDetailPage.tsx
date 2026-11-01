import { useCallback, useEffect, useState } from 'react';
import styled from 'styled-components';
import { addChannel, getLineup } from '../api/lineups.js';
import { ChannelFieldsForm } from '../components/ChannelFieldsForm';
import {
  emptyChannelFieldValues,
  toChannelRequestBody,
  type ChannelFieldValues,
} from '../components/channelFormValues';
import { ChannelRow } from '../components/ChannelRow';
import { SdLineupIdsEditor } from '../components/SdLineupIdsEditor';
import { SyncAndGeneratePanel } from '../components/SyncAndGeneratePanel';
import type { Channel, Lineup } from '../types';
import {
  Card,
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
 * Detail view for a single lineup: its SD lineup associations, channel
 * list (with per-channel edit/delete/mapping actions), and a form to add
 * a channel manually. No mapping suggestion/bulk-accept UI yet (Phase 3)
 * - mapping is plain manual entry per the Phase 1 backend contract.
 */
export function LineupDetailPage({ lineupId, onBack }: LineupDetailPageProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

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
      </BackRow>

      {state.status === 'loading' && <p>Loading lineup...</p>}
      {state.status === 'error' && (
        <ErrorText>Failed to load lineup: {state.message}</ErrorText>
      )}
      {state.status === 'ok' && (
        <>
          <SectionTitle>{state.lineup.name}</SectionTitle>
          <Meta>
            Source: {state.lineup.source} · {state.lineup.channels.length} channel
            {state.lineup.channels.length === 1 ? '' : 's'} · created {state.lineup.createdAt}
          </Meta>

          <SubsectionTitle>Sync & Generate</SubsectionTitle>
          <SyncAndGeneratePanel lineupId={lineupId} />

          <SubsectionTitle>SchedulesDirect lineups</SubsectionTitle>
          <SdLineupIdsEditor
            lineupId={lineupId}
            sdLineupIds={state.lineup.sdLineupIds}
            onChanged={handleSdLineupIdsChanged}
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
