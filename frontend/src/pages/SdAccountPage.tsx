import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import {
  addSdAccountLineup,
  getSdAccountLineupLimit,
  listSdAccountLineups,
  removeSdAccountLineup,
} from '../api/sdAccount.js';
import type { SdAccountLineup, SdAccountLineupLimit, SdAddRemoveLineupResponse } from '../types';
import {
  Button,
  Card,
  DangerButton,
  ErrorText,
  FormActions,
  HelperText,
  Input,
  Label,
  Page,
  SectionTitle,
  StrongWarningText,
  SubsectionTitle,
} from '../styles/primitives';

const LimitCard = styled(Card)<{ $warn: boolean }>`
  margin-bottom: 24px;
  background: ${({ $warn }) => ($warn ? '#fdf6e3' : '#f4f8f4')};
  border-color: ${({ $warn }) => ($warn ? '#e3c97e' : '#bfe3bf')};
`;

const LimitSummary = styled.p`
  margin: 0;
  font-size: 15px;
  font-weight: 600;
`;

const LimitNote = styled.p`
  margin: 6px 0 0;
  font-size: 13px;
  color: #7a5a00;
`;

const LineupListEl = styled.ul`
  list-style: none;
  margin: 0 0 24px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const LineupItem = styled.li`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  flex-wrap: wrap;
`;

const LineupInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const LineupName = styled.span`
  font-size: 15px;
  font-weight: 600;
`;

const Meta = styled.span`
  font-size: 13px;
  color: #666;
  font-family: ui-monospace, monospace;
`;

const AddForm = styled.form`
  display: flex;
  gap: 8px;
  align-items: flex-end;
  flex-wrap: wrap;
`;

const SuccessText = styled.p`
  color: #2a6b2a;
  font-size: 14px;
  margin: 8px 0;
`;

type LimitState =
  | { status: 'loading' }
  | { status: 'ok'; limit: SdAccountLineupLimit }
  | { status: 'error'; message: string };

type LineupsState =
  | { status: 'loading' }
  | { status: 'ok'; lineups: SdAccountLineup[] }
  | { status: 'error'; message: string };

type AddState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'done'; message: string }
  | { status: 'error'; message: string };

/**
 * Manages the user's real SchedulesDirect *account* lineups (SD's own
 * headend subscriptions) via `/api/sd-account/*` - entirely distinct from
 * epg-editor's own lineups (`LineupsListPage`/`LineupDetailPage`) and from
 * `LineupDetailPage`'s `SdLineupIdsEditor` (which only edits which SD
 * lineup ID *strings* one of epg-editor's own lineups references locally).
 *
 * Fetches and shows the account's lineup-slot usage up front (before the
 * add form is even touched), per CLAUDE.md's Core workflow 2 - "surface
 * that limit in the UI rather than discovering it via a failed API call."
 *
 * There is no SD postal-code/headend-lookup endpoint yet, so adding a
 * lineup requires the user to already know the exact SD lineup ID string -
 * an accepted stopgap (see the add form's helper text), not something this
 * page tries to work around with a picker/search UI.
 */
export function SdAccountPage() {
  const [limitState, setLimitState] = useState<LimitState>({ status: 'loading' });
  const [lineupsState, setLineupsState] = useState<LineupsState>({ status: 'loading' });
  // Per-lineup in-flight tracking (not a single shared id) so removing two
  // different lineups concurrently can't let either button's disabled state
  // - or the "finally" cleanup - clobber the other's in-flight status.
  const [removingIds, setRemovingIds] = useState<Set<string>>(() => new Set());
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [newLineupId, setNewLineupId] = useState('');
  const [addState, setAddState] = useState<AddState>({ status: 'idle' });
  const addInFlightRef = useRef(false);
  // Sequence counters so a slower, stale request resolving after a newer
  // one for the same loader can't overwrite fresher state.
  const limitRequestIdRef = useRef(0);
  const lineupsRequestIdRef = useRef(0);

  const loadLimit = useCallback(() => {
    const requestId = ++limitRequestIdRef.current;
    (getSdAccountLineupLimit() as Promise<SdAccountLineupLimit>)
      .then((limit) => {
        if (requestId !== limitRequestIdRef.current) {
          return;
        }
        setLimitState({ status: 'ok', limit });
      })
      .catch((error: unknown) => {
        if (requestId !== limitRequestIdRef.current) {
          return;
        }
        setLimitState({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        });
      });
  }, []);

  const loadLineups = useCallback(() => {
    const requestId = ++lineupsRequestIdRef.current;
    (listSdAccountLineups() as Promise<SdAccountLineup[]>)
      .then((lineups) => {
        if (requestId !== lineupsRequestIdRef.current) {
          return;
        }
        setLineupsState({ status: 'ok', lineups });
      })
      .catch((error: unknown) => {
        if (requestId !== lineupsRequestIdRef.current) {
          return;
        }
        setLineupsState({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        });
      });
  }, []);

  useEffect(() => {
    loadLimit();
    loadLineups();
  }, [loadLimit, loadLineups]);

  function refreshAfterMutation() {
    setLimitState({ status: 'loading' });
    setLineupsState({ status: 'loading' });
    loadLimit();
    loadLineups();
  }

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    const trimmed = newLineupId.trim();
    if (!trimmed || addInFlightRef.current) {
      return;
    }
    addInFlightRef.current = true;
    setAddState({ status: 'submitting' });
    setRemoveError(null);
    try {
      const response = (await addSdAccountLineup(trimmed)) as SdAddRemoveLineupResponse;
      setAddState({
        status: 'done',
        message: response.message ?? `Added lineup "${trimmed}".`,
      });
      setNewLineupId('');
      refreshAfterMutation();
    } catch (error) {
      setAddState({
        status: 'error',
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      addInFlightRef.current = false;
    }
  }

  async function handleRemove(lineup: SdAccountLineup) {
    const lineupId = lineup.lineup;
    if (removingIds.has(lineupId)) {
      return;
    }
    const confirmed = window.confirm(
      `Unsubscribe from lineup "${lineup.name}" (${lineupId})? This removes it from your ` +
        'SchedulesDirect account, not just from epg-editor.',
    );
    if (!confirmed) {
      return;
    }
    setRemovingIds((prev) => new Set(prev).add(lineupId));
    setRemoveError(null);
    // Clear a stale add-flow message left over from an earlier, unrelated
    // action - but only once the add really is finished, so we never hide
    // an "Adding..." state that's still genuinely in flight.
    setAddState((prev) => (prev.status === 'submitting' ? prev : { status: 'idle' }));
    try {
      await removeSdAccountLineup(lineupId);
      refreshAfterMutation();
    } catch (error) {
      setRemoveError(error instanceof Error ? error.message : String(error));
    } finally {
      setRemovingIds((prev) => {
        const next = new Set(prev);
        next.delete(lineupId);
        return next;
      });
    }
  }

  const limit = limitState.status === 'ok' ? limitState.limit : null;
  const atLimit =
    limit !== null && limit.maxLineups !== null && limit.lineupsUsed >= limit.maxLineups;
  const addDisabled = addState.status === 'submitting';

  return (
    <Page>
      <SectionTitle>SchedulesDirect account lineups</SectionTitle>
      <HelperText>
        Manage the lineups actually subscribed on your SchedulesDirect account (SD&apos;s own
        headend subscriptions) - separate from epg-editor&apos;s own lineups, and separate from
        which SD lineup IDs an epg-editor lineup is associated with (set on each lineup&apos;s
        detail page).
      </HelperText>

      {limitState.status === 'loading' && <p>Loading slot usage...</p>}
      {limitState.status === 'error' && (
        <ErrorText>Failed to load lineup-slot usage: {limitState.message}</ErrorText>
      )}
      {limit && (
        <LimitCard $warn={atLimit}>
          <LimitSummary>
            {limit.maxLineups !== null
              ? `${limit.lineupsUsed} of ${limit.maxLineups} lineup slots used`
              : `${limit.lineupsUsed} lineup slots used (account limit unknown)`}
            {atLimit && ' - at limit'}
          </LimitSummary>
          {limit.deletedLineupCount > 0 && (
            <LimitNote>
              {limit.deletedLineupCount} of those {limit.lineupsUsed} are flagged as removed by
              SD but may or may not still count against your limit.
            </LimitNote>
          )}
          {atLimit && (
            <LimitNote>
              You&apos;re at (or over) your account&apos;s lineup limit. Adding another lineup
              will likely be rejected by SchedulesDirect until you remove one.
            </LimitNote>
          )}
        </LimitCard>
      )}

      <SubsectionTitle>Subscribed lineups</SubsectionTitle>
      {lineupsState.status === 'loading' && <p>Loading lineups...</p>}
      {lineupsState.status === 'error' && (
        <ErrorText>Failed to load account lineups: {lineupsState.message}</ErrorText>
      )}
      {removeError && <ErrorText>Failed to remove lineup: {removeError}</ErrorText>}
      {lineupsState.status === 'ok' &&
        (lineupsState.lineups.length === 0 ? (
          <p>No lineups subscribed on this account yet.</p>
        ) : (
          <LineupListEl>
            {lineupsState.lineups.map((lineup) => (
              <LineupItem key={lineup.lineup}>
                <LineupInfo>
                  <LineupName>{lineup.name}</LineupName>
                  <Meta>
                    {lineup.lineup}
                    {lineup.transport ? ` · ${lineup.transport}` : ''}
                    {lineup.location ? ` · ${lineup.location}` : ''}
                  </Meta>
                </LineupInfo>
                <DangerButton
                  type="button"
                  disabled={removingIds.has(lineup.lineup)}
                  onClick={() => handleRemove(lineup)}
                >
                  {removingIds.has(lineup.lineup) ? 'Removing...' : 'Remove'}
                </DangerButton>
              </LineupItem>
            ))}
          </LineupListEl>
        ))}

      <SubsectionTitle>Add a lineup</SubsectionTitle>
      {atLimit && (
        <StrongWarningText>
          You&apos;re at (or over) your account&apos;s lineup limit - adding another will likely
          be rejected by SchedulesDirect until you remove one.
        </StrongWarningText>
      )}
      <AddForm onSubmit={handleAdd}>
        <Label>
          SD lineup ID
          <Input
            type="text"
            placeholder="e.g. USA-OTA12345"
            value={newLineupId}
            onChange={(event) => setNewLineupId(event.target.value)}
            disabled={addDisabled}
          />
        </Label>
        <FormActions>
          <Button type="submit" disabled={addDisabled || !newLineupId.trim()}>
            {addDisabled ? 'Adding...' : atLimit ? 'Add lineup (at limit)' : 'Add lineup'}
          </Button>
        </FormActions>
      </AddForm>
      <HelperText>
        Find your lineup ID via SchedulesDirect&apos;s own lineup lookup tools - epg-editor
        doesn&apos;t yet offer a postal-code/headend search, so you&apos;ll need the exact
        lineup ID string (e.g. &quot;USA-OTA12345&quot;) in hand before adding it here.
      </HelperText>
      {addState.status === 'done' && <SuccessText>{addState.message}</SuccessText>}
      {addState.status === 'error' && (
        <ErrorText>Failed to add lineup: {addState.message}</ErrorText>
      )}
    </Page>
  );
}
