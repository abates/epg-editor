import { useRef, useState } from 'react';
import styled, { keyframes } from 'styled-components';
import { refreshNow } from '../api/refresh.js';
import type { RefreshResult } from '../types';
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

const RefreshButton = styled(Button)`
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

type RefreshState =
  | { status: 'idle' }
  | { status: 'refreshing' }
  | { status: 'done'; result: RefreshResult }
  | { status: 'error'; message: string };

/**
 * Triggers `POST /api/refresh-now`: an immediate, real-network run of the
 * global SD refresh + XMLTV regeneration pipeline across *every*
 * epg-editor lineup - the manual "do it now" counterpart to the
 * APScheduler job that runs the exact same pipeline on a timer
 * (`EPG_EDITOR_REFRESH_INTERVAL` hours). Triggering this doesn't reset or
 * otherwise affect that schedule.
 *
 * Replaces the old per-lineup "Sync & Generate" panel (removed) - this one
 * isn't scoped to a single lineup, so it lives on the lineups list page
 * rather than a lineup detail page.
 *
 * The backend has no guard against two overlapping manual-refresh calls,
 * so this component is the only thing preventing a double-click from
 * firing a second request while one is in flight. That guard is a
 * synchronous ref check (`refreshInFlightRef`), not just the `disabled`
 * attribute on the button - the attribute only takes effect after a
 * re-render, so a second click that lands before that re-render commits
 * would otherwise slip through.
 */
export function RefreshNowPanel() {
  const [state, setState] = useState<RefreshState>({ status: 'idle' });
  const refreshInFlightRef = useRef(false);

  async function handleClick() {
    if (refreshInFlightRef.current) {
      return;
    }
    refreshInFlightRef.current = true;
    setState({ status: 'refreshing' });
    try {
      const result = (await refreshNow()) as RefreshResult;
      setState({ status: 'done', result });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      refreshInFlightRef.current = false;
    }
  }

  const refreshing = state.status === 'refreshing';
  const hasErrors = state.status === 'done' && state.result.errors.length > 0;

  return (
    <div>
      <RefreshButton type="button" disabled={refreshing} onClick={handleClick}>
        {refreshing && <Spinner aria-hidden="true" />}
        {refreshing ? 'Refreshing...' : 'Refresh Now'}
      </RefreshButton>
      <HelperText>
        Fetches fresh schedule/program data from SchedulesDirect for every
        lineup and regenerates each lineup's XMLTV file. Runs the same
        pipeline as the scheduled background refresh, just immediately
        instead of waiting for it - this does not change the schedule
        itself. This hits the real SD API and can take anywhere from a
        few seconds to a few minutes depending on how much is stale.
      </HelperText>

      {state.status === 'done' && (
        <ResultCard>
          <ResultSummary>
            Processed {state.result.lineupsProcessed} lineup
            {state.result.lineupsProcessed === 1 ? '' : 's'} (
            {state.result.lineupsRegenerated} regenerated). Refreshed{' '}
            {state.result.stationRostersRefreshed} station roster
            {state.result.stationRostersRefreshed === 1 ? '' : 's'} (
            {state.result.stationRostersSkipped} skipped, already current).
            Checked {state.result.scheduleDaysChecked} schedule-day
            {state.result.scheduleDaysChecked === 1 ? '' : 's'} (
            {state.result.scheduleDaysRefetched} refetched,{' '}
            {state.result.scheduleDaysSkippedUnchanged} unchanged). Fetched{' '}
            {state.result.programsFetched} program
            {state.result.programsFetched === 1 ? '' : 's'}.
          </ResultSummary>
        </ResultCard>
      )}

      {hasErrors && state.status === 'done' && (
        <WarningCard>
          <ResultSummary>
            Completed with partial failures - some lineups, SD lineups, or
            stations did not refresh successfully:
          </ResultSummary>
          <ErrorList>
            {state.result.errors.map((error, index) => (
              <li key={`${error.scope}-${error.id ?? 'none'}-${index}`}>
                {error.scope}
                {error.id ? ` (${error.id})` : ''}: {error.message}
              </li>
            ))}
          </ErrorList>
        </WarningCard>
      )}

      {state.status === 'error' && (
        <ErrorText>Refresh failed: {state.message}</ErrorText>
      )}
    </div>
  );
}
