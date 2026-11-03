import { useEffect, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { setChannelMapping } from '../api/lineups.js';
import { searchStations } from '../api/stations.js';
import type { Channel, StationSearchCandidate, StationSearchResult } from '../types';
import {
  Button,
  CheckboxLabel,
  ErrorText,
  FormActions,
  FormGrid,
  HelperText,
  Input,
  Label,
  SecondaryButton,
} from '../styles/primitives';
import { confidenceTone } from './mappingConfidence';
import { StatusBadge } from './StatusBadge';

interface ChannelMappingFormProps {
  lineupId: string;
  channel: Channel;
  sdLineupIds: string[];
  onSaved: (channel: Channel) => void;
  onCancel: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;
// Matches the backend's STATION_SEARCH_DEFAULT_LIMIT (see
// `backend/app/services/suggestions.py`) - kept as an explicit constant here
// (rather than omitting `limit` and relying on the backend default) so this
// value is visible alongside the "showing N of M" UI copy that depends on
// it.
const SEARCH_RESULT_LIMIT = 25;

const SearchSection = styled.div`
  margin-bottom: 12px;
`;

const SelectedSummary = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #f7f9fc;
  font-size: 13px;
`;

const SelectedText = styled.span`
  color: #222;
`;

const ResultsList = styled.ul`
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 260px;
  overflow-y: auto;
`;

const ResultItem = styled.button<{ $selected: boolean }>`
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  font-size: 13px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid ${({ $selected }) => ($selected ? '#1456b8' : '#e0e0e0')};
  background: ${({ $selected }) => ($selected ? '#eaf1fc' : '#fff')};
  cursor: pointer;

  &:hover:not(:disabled) {
    background: #f2f6fc;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
`;

const ResultText = styled.span`
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-width: 0;
`;

const ResultName = styled.span`
  color: #222;
  font-weight: 500;
`;

const ResultMeta = styled.span`
  color: #666;
  font-family: ui-monospace, monospace;
  font-size: 12px;
`;

const Logo = styled.img`
  width: 28px;
  height: 28px;
  object-fit: contain;
  border-radius: 3px;
  background: #fff;
  border: 1px solid #ddd;
  flex-shrink: 0;
`;

/**
 * Directly sets a channel's SD station mapping.
 *
 * Defaults to a search-and-select mode: a debounced free-text search against
 * `GET /api/lineups/{lineupId}/station-search` (backlog item 37), which also
 * supports "browse mode" (empty query returns the lineup's full cached
 * candidate pool) so a small roster can be scrolled without typing anything.
 * Picking a result just populates the same `sdStationId`/`sdLineupId` this
 * form always submitted via `setChannelMapping` - search is a convenience
 * over manual entry, not a different submission path.
 *
 * Raw `sdStationId`/`sdLineupId` text entry (this form's only mode before
 * Phase 3's suggestion UI existed) is kept available as an escape hatch
 * behind an "Enter manually" toggle, collapsed by default, for stations that
 * genuinely can't be found by search (e.g. a station missing from SD's own
 * metadata).
 */
export function ChannelMappingForm({
  lineupId,
  channel,
  sdLineupIds,
  onSaved,
  onCancel,
}: ChannelMappingFormProps) {
  const [sdStationId, setSdStationId] = useState(channel.mapping?.sdStationId ?? '');
  const [sdLineupId, setSdLineupId] = useState(channel.mapping?.sdLineupId ?? '');
  const [confirmed, setConfirmed] = useState(channel.mapping?.confirmed ?? true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StationSearchCandidate[]>([]);
  const [candidatePoolSize, setCandidatePoolSize] = useState(0);
  const [uncachedSdLineupIds, setUncachedSdLineupIds] = useState<string[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<StationSearchCandidate | null>(null);

  // Debounced search-as-you-type: fires immediately (no delay) for the
  // initial empty-query "browse mode" load, debounces subsequent keystrokes
  // so typing doesn't hammer the backend on every character. `cancelled`
  // guards against a slower, now-stale request's response landing after a
  // newer one already has (e.g. a fast second keystroke outracing the first
  // request's response).
  useEffect(() => {
    let cancelled = false;
    setSearchLoading(true);
    setSearchError(null);
    const delay = query.trim() ? SEARCH_DEBOUNCE_MS : 0;
    const timer = setTimeout(() => {
      searchStations(lineupId, { q: query, limit: SEARCH_RESULT_LIMIT })
        .then((result) => {
          if (cancelled) return;
          const typed = result as StationSearchResult;
          setResults(typed.results);
          setCandidatePoolSize(typed.candidatePoolSize);
          setUncachedSdLineupIds(typed.uncachedSdLineupIds);
        })
        .catch((err) => {
          if (cancelled) return;
          setSearchError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          if (!cancelled) {
            setSearchLoading(false);
          }
        });
    }, delay);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [lineupId, query]);

  function handleSelect(candidate: StationSearchCandidate) {
    setSdStationId(candidate.stationID);
    setSdLineupId(candidate.sdLineupId);
    setSelected(candidate);
  }

  function handleManualStationIdChange(value: string) {
    setSdStationId(value);
    setSelected(null);
  }

  function handleManualLineupIdChange(value: string) {
    setSdLineupId(value);
    setSelected(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!sdStationId.trim() || !sdLineupId.trim()) {
      setError('Both sdStationId and sdLineupId are required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = (await setChannelMapping(lineupId, channel.id, {
        sdStationId: sdStationId.trim(),
        sdLineupId: sdLineupId.trim(),
        confirmed,
      })) as Channel;
      onSaved(updated);
    } catch (err) {
      // `error.message` is the backend's human-readable detail (e.g. the
      // 400 "sdLineupId isn't associated with this lineup" message) -
      // `api/lineups.js` strips the method/path/status noise before
      // throwing, so it's safe to surface directly to the user.
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  // Dedupe defensively - `uncachedSdLineupIds` is documented as a set but
  // not guaranteed unique by the backend.
  const uniqueUncached = Array.from(new Set(uncachedSdLineupIds));
  const trimmedQuery = query.trim();
  const trimmedStationId = sdStationId.trim();
  const trimmedLineupId = sdLineupId.trim();
  const hasSelection = trimmedStationId !== '' && trimmedLineupId !== '';
  // `selected` is kept only as a convenience cache of a search result's
  // name/logo so the summary doesn't need a redundant lookup - it is never
  // trusted as the source of truth for *what's* currently selected (that's
  // always `sdStationId`/`sdLineupId`). Only treat it as display-worthy when
  // it still matches the current form values; manual entry can diverge it
  // (also defensively cleared in the manual `onChange` handlers above).
  const selectedMatchesCurrent =
    selected !== null && selected.stationID === trimmedStationId && selected.sdLineupId === trimmedLineupId;

  return (
    <form onSubmit={handleSubmit}>
      {hasSelection && (
        <SelectedSummary>
          {selectedMatchesCurrent && selected?.logoUrl && <Logo src={selected.logoUrl} alt="" />}
          <SelectedText>
            Selected:{' '}
            {selectedMatchesCurrent && selected
              ? `${selected.name}${selected.callsign ? ` (${selected.callsign})` : ''} - station ${selected.stationID} in ${selected.sdLineupId}`
              : `station ${trimmedStationId} in ${trimmedLineupId}`}
          </SelectedText>
        </SelectedSummary>
      )}

      {!showAdvanced && (
        <SearchSection>
          <Label>
            Search SD stations
            <Input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                }
              }}
              placeholder="Search by name, callsign, or affiliate..."
              disabled={submitting}
            />
          </Label>

          {uniqueUncached.length > 0 && (
            <HelperText>
              {uniqueUncached.length} of your associated SD lineup
              {uniqueUncached.length === 1 ? '' : 's'} ({uniqueUncached.join(', ')}) haven't been
              fetched yet - generate suggestions or wait for the next refresh for a complete
              picker.
            </HelperText>
          )}

          {searchLoading && <HelperText>{trimmedQuery ? 'Searching...' : 'Loading stations...'}</HelperText>}
          {searchError && <ErrorText>{searchError}</ErrorText>}

          {!searchLoading && !searchError && results.length === 0 && uniqueUncached.length === 0 && (
            <HelperText>
              {trimmedQuery
                ? `No stations matched "${trimmedQuery}".`
                : "No cached stations available yet for this lineup's associated SD lineups."}
            </HelperText>
          )}

          {!searchLoading && !searchError && results.length > 0 && (
            <>
              <ResultsList>
                {results.map((candidate) => {
                  const key = `${candidate.sdLineupId}:${candidate.stationID}`;
                  const isSelected =
                    candidate.stationID === trimmedStationId && candidate.sdLineupId === trimmedLineupId;
                  return (
                    <ResultItem
                      key={key}
                      type="button"
                      $selected={isSelected}
                      disabled={submitting}
                      onClick={() => handleSelect(candidate)}
                    >
                      {candidate.logoUrl && <Logo src={candidate.logoUrl} alt="" />}
                      <ResultText>
                        <ResultName>
                          {candidate.name}
                          {candidate.callsign ? ` (${candidate.callsign})` : ''}
                        </ResultName>
                        <ResultMeta>
                          {candidate.affiliate ? `${candidate.affiliate} - ` : ''}
                          station {candidate.stationID} in {candidate.sdLineupId}
                        </ResultMeta>
                      </ResultText>
                      {candidate.score > 0 && (
                        <StatusBadge $tone={confidenceTone(candidate.score)}>
                          {Math.round(candidate.score * 100)}%
                        </StatusBadge>
                      )}
                    </ResultItem>
                  );
                })}
              </ResultsList>
              {!trimmedQuery && candidatePoolSize > results.length && (
                <HelperText>
                  Showing {results.length} of {candidatePoolSize} - type to narrow.
                </HelperText>
              )}
            </>
          )}
        </SearchSection>
      )}

      <FormActions>
        <SecondaryButton type="button" onClick={() => setShowAdvanced((prev) => !prev)}>
          {showAdvanced ? 'Use search' : "Can't find it? Enter manually"}
        </SecondaryButton>
      </FormActions>

      {showAdvanced && (
        <FormGrid>
          <Label>
            SD station id
            <Input
              type="text"
              value={sdStationId}
              onChange={(event) => handleManualStationIdChange(event.target.value)}
              disabled={submitting}
              required
            />
          </Label>
          <Label>
            SD lineup id
            <Input
              type="text"
              value={sdLineupId}
              onChange={(event) => handleManualLineupIdChange(event.target.value)}
              disabled={submitting}
              required
            />
          </Label>
        </FormGrid>
      )}

      {sdLineupIds.length > 0 ? (
        <HelperText>Lineup's associated SD lineups: {sdLineupIds.join(', ')}</HelperText>
      ) : (
        <HelperText>
          This lineup has no associated SD lineup ids yet - the mapping will be rejected
          until you add one below.
        </HelperText>
      )}
      <FormActions>
        <CheckboxLabel>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            disabled={submitting}
          />
          Confirmed
        </CheckboxLabel>
      </FormActions>
      <FormActions>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving...' : 'Save mapping'}
        </Button>
        <SecondaryButton type="button" disabled={submitting} onClick={onCancel}>
          Cancel
        </SecondaryButton>
      </FormActions>
      {error && <ErrorText>{error}</ErrorText>}
    </form>
  );
}
