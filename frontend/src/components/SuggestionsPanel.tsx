import { useRef, useState } from 'react';
import styled from 'styled-components';
import { bulkAcceptSuggestions, generateSuggestions, getLineup } from '../api/lineups.js';
import type { BulkAcceptResult, Channel, Lineup, SuggestionResult } from '../types';
import { Button, Card, ErrorText, FormActions, HelperText, SecondaryButton } from '../styles/primitives';

const ResultCard = styled(Card)`
  margin-top: 12px;
  background: #f4f8f4;
  border-color: #bfe3bf;
`;

const ResultSummary = styled.p`
  margin: 0;
  font-size: 14px;
`;

const ConfirmedList = styled.ul`
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 13px;
`;

type PanelState =
  | { status: 'idle' }
  | { status: 'generating' }
  | { status: 'generated'; result: SuggestionResult }
  | { status: 'bulk-accepting' }
  | { status: 'bulk-accepted'; result: BulkAcceptResult }
  | { status: 'error'; message: string };

interface SuggestionsPanelProps {
  lineupId: string;
  channels: Channel[];
  onRefreshed: (lineup: Lineup) => void;
}

/**
 * Lineup-level mapping-suggestion actions: (re)generate candidate SD
 * station suggestions for every channel, and bulk-accept the unambiguous
 * near-exact matches at the backend's fixed confidence threshold (`0.92` -
 * not a UI control, per CLAUDE.md's Core workflow #4).
 *
 * Neither endpoint's response body includes the actual suggestions or
 * updated mappings (see `SuggestionResult`/`BulkAcceptResult`) - those land
 * on each channel's own `mapping` field, so after either action succeeds
 * this re-fetches the whole lineup (`getLineup`) and hands it to the parent
 * page via `onRefreshed` rather than trying to merge a partial response
 * into stale local state - a bulk multi-channel update like this is exactly
 * where a hand-rolled local merge could drift from the server's actual
 * state.
 *
 * Same double-click guard pattern as `SyncAndGeneratePanel`: a synchronous
 * ref, not just `disabled`, since the backend has no concurrency guard of
 * its own for either endpoint. Both actions share one guard/ref - they
 * both mutate the same channels' mapping state for this lineup, so running
 * them concurrently (e.g. a bulk-accept racing a suggestion regeneration)
 * isn't safe to allow.
 */
export function SuggestionsPanel({ lineupId, channels, onRefreshed }: SuggestionsPanelProps) {
  const [state, setState] = useState<PanelState>({ status: 'idle' });
  const actionInFlightRef = useRef(false);

  const busy = state.status === 'generating' || state.status === 'bulk-accepting';

  async function handleGenerate() {
    if (actionInFlightRef.current) {
      return;
    }
    actionInFlightRef.current = true;
    setState({ status: 'generating' });
    try {
      const result = (await generateSuggestions(lineupId)) as SuggestionResult;
      const lineup = (await getLineup(lineupId)) as Lineup;
      onRefreshed(lineup);
      setState({ status: 'generated', result });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      actionInFlightRef.current = false;
    }
  }

  async function handleBulkAccept() {
    if (actionInFlightRef.current) {
      return;
    }
    actionInFlightRef.current = true;
    setState({ status: 'bulk-accepting' });
    try {
      const result = (await bulkAcceptSuggestions(lineupId)) as BulkAcceptResult;
      const lineup = (await getLineup(lineupId)) as Lineup;
      onRefreshed(lineup);
      setState({ status: 'bulk-accepted', result });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      actionInFlightRef.current = false;
    }
  }

  function describeChannel(channelId: string): string {
    const channel = channels.find((candidate) => candidate.id === channelId);
    return channel ? channel.name : channelId;
  }

  return (
    <div>
      <FormActions>
        <Button type="button" disabled={busy} onClick={handleGenerate}>
          {state.status === 'generating' ? 'Generating...' : 'Generate Suggestions'}
        </Button>
        <SecondaryButton type="button" disabled={busy} onClick={handleBulkAccept}>
          {state.status === 'bulk-accepting' ? 'Accepting...' : 'Bulk-Accept Suggestions'}
        </SecondaryButton>
      </FormActions>
      <HelperText>
        Generate scores every channel against candidate SchedulesDirect stations from this
        lineup's associated SD lineups (a real SD-network call - can take a few seconds).
        Bulk-accept confirms channels whose top suggestion is unambiguously highest-scoring and
        meets the backend's fixed confidence threshold; everything else is left for manual
        review in the channel list below.
      </HelperText>

      {state.status === 'generated' && (
        <ResultCard>
          <ResultSummary>
            Scored {state.result.channelsScored} channel
            {state.result.channelsScored === 1 ? '' : 's'} against{' '}
            {state.result.stationPoolSize} candidate station
            {state.result.stationPoolSize === 1 ? '' : 's'}.
          </ResultSummary>
        </ResultCard>
      )}

      {state.status === 'bulk-accepted' && (
        <ResultCard>
          <ResultSummary>
            Confirmed {state.result.confirmedCount} channel
            {state.result.confirmedCount === 1 ? '' : 's'} at or above the{' '}
            {Math.round(state.result.threshold * 100)}% threshold.
          </ResultSummary>
          {state.result.confirmed.length > 0 && (
            <ConfirmedList>
              {state.result.confirmed.map((item) => (
                <li key={item.channelId}>
                  {describeChannel(item.channelId)} &rarr; station {item.sdStationId} (
                  {Math.round(item.score * 100)}%)
                </li>
              ))}
            </ConfirmedList>
          )}
        </ResultCard>
      )}

      {state.status === 'error' && <ErrorText>{state.message}</ErrorText>}
    </div>
  );
}
