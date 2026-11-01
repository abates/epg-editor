import { useRef, useState } from 'react';
import styled, { keyframes } from 'styled-components';
import { syncAndGenerate } from '../api/lineups.js';
import type { SyncResult } from '../types';
import { Button, Card, ErrorText, HelperText } from '../styles/primitives';

const spin = keyframes`
  to {
    transform: rotate(360deg);
  }
`;

const Spinner = styled.span`
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.5);
  border-top-color: white;
  border-radius: 50%;
  animation: ${spin} 0.8s linear infinite;
`;

const SyncButton = styled(Button)`
  display: inline-flex;
  align-items: center;
  gap: 8px;
`;

const ResultCard = styled(Card)`
  margin-top: 12px;
  background: #f4f8f4;
  border-color: #bfe3bf;
`;

const WarningCard = styled(Card)`
  margin-top: 12px;
  background: #fdf6e3;
  border-color: #e3c97e;
`;

const ErrorList = styled.ul`
  margin: 8px 0 0;
  padding-left: 20px;
  color: #7a5a00;
  font-size: 13px;
`;

const ResultSummary = styled.p`
  margin: 0;
  font-size: 14px;
`;

const XmltvLink = styled.a`
  display: inline-block;
  margin-top: 8px;
  font-size: 13px;
`;

type SyncState =
  | { status: 'idle' }
  | { status: 'syncing' }
  | { status: 'done'; result: SyncResult }
  | { status: 'error'; message: string };

interface SyncAndGeneratePanelProps {
  lineupId: string;
}

/**
 * Triggers `POST /api/lineups/{lineupId}/sync-and-generate`: a slow, real
 * SchedulesDirect-network call that fetches schedule/program data for
 * every confirmed-mapped channel and regenerates the lineup's XMLTV file.
 *
 * The backend has no guard against two overlapping syncs for the same
 * lineup, so this component is the only thing preventing a double-click
 * from firing a second request while one is in flight. That guard is a
 * synchronous ref check (`syncInFlightRef`), not just the `disabled`
 * attribute on the button - the attribute only takes effect after a
 * re-render, so a second click that lands before that re-render commits
 * would otherwise slip through.
 */
export function SyncAndGeneratePanel({ lineupId }: SyncAndGeneratePanelProps) {
  const [state, setState] = useState<SyncState>({ status: 'idle' });
  const syncInFlightRef = useRef(false);

  async function handleClick() {
    if (syncInFlightRef.current) {
      return;
    }
    syncInFlightRef.current = true;
    setState({ status: 'syncing' });
    try {
      const result = (await syncAndGenerate(lineupId)) as SyncResult;
      setState({ status: 'done', result });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      syncInFlightRef.current = false;
    }
  }

  const syncing = state.status === 'syncing';
  const hasPartialFailures =
    state.status === 'done' &&
    (state.result.stationErrors.length > 0 || state.result.errors.length > 0);

  return (
    <div>
      <SyncButton type="button" disabled={syncing} onClick={handleClick}>
        {syncing && <Spinner aria-hidden="true" />}
        {syncing ? 'Syncing...' : 'Sync & Generate'}
      </SyncButton>
      <HelperText>
        Fetches fresh schedule/program data from SchedulesDirect for every
        confirmed-mapped channel and regenerates this lineup's XMLTV file.
        This hits the real SD API and can take anywhere from a few seconds
        to tens of seconds.
      </HelperText>

      {state.status === 'done' && (
        <ResultCard>
          <ResultSummary>
            Synced {state.result.stationsSynced} station
            {state.result.stationsSynced === 1 ? '' : 's'}, fetched{' '}
            {state.result.scheduleDaysFetched} schedule-day
            {state.result.scheduleDaysFetched === 1 ? '' : 's'} and{' '}
            {state.result.programsFetched} program
            {state.result.programsFetched === 1 ? '' : 's'}, generated XMLTV
            for {state.result.channelsGenerated} channel
            {state.result.channelsGenerated === 1 ? '' : 's'}.
          </ResultSummary>
          <XmltvLink href={`/xmltv/${lineupId}.xml`} target="_blank" rel="noreferrer">
            View generated XMLTV &rarr;
          </XmltvLink>
        </ResultCard>
      )}

      {hasPartialFailures && state.status === 'done' && (
        <WarningCard>
          <ResultSummary>
            Completed with partial failures - some stations or steps did not
            sync successfully:
          </ResultSummary>
          {state.result.stationErrors.length > 0 && (
            <ErrorList>
              {state.result.stationErrors.map((stationError, index) => (
                <li key={`${stationError.sdStationId}-${index}`}>
                  Station {stationError.sdStationId}: {stationError.message}
                </li>
              ))}
            </ErrorList>
          )}
          {state.result.errors.length > 0 && (
            <ErrorList>
              {state.result.errors.map((message, index) => (
                <li key={index}>{message}</li>
              ))}
            </ErrorList>
          )}
        </WarningCard>
      )}

      {state.status === 'error' && (
        <ErrorText>Sync & Generate failed: {state.message}</ErrorText>
      )}
    </div>
  );
}
