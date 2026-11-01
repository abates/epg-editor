import { useState } from 'react';
import styled from 'styled-components';
import { setChannelMapping } from '../api/lineups.js';
import type { Channel, MappingSuggestion } from '../types';
import { Button, ErrorText, SecondaryButton } from '../styles/primitives';
import { StatusBadge, type StatusTone } from './StatusBadge';

const Wrapper = styled.div`
  margin-top: 4px;
`;

const Label = styled.span`
  font-size: 13px;
  font-weight: 600;
  color: #444;
`;

const List = styled.ul`
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
`;

const Item = styled.li`
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
`;

const StationId = styled.span`
  font-family: ui-monospace, monospace;
  color: #444;
`;

interface ChannelSuggestionsProps {
  lineupId: string;
  channel: Channel;
  onChanged: (channel: Channel) => void;
}

/**
 * Lists a channel's candidate mapping suggestions (already sorted
 * best-first by the backend - see `docs/data-model.md`'s `suggestions`
 * notes) with an Accept/Reject action per suggestion.
 *
 * Renders nothing if the channel's mapping is already confirmed (nothing
 * to review) or `mapping.suggestions` is empty (nothing generated yet, or
 * no clean match was found).
 *
 * - Accept calls the existing `setChannelMapping` mapping-confirm endpoint
 *   with that suggestion's own `sdStationId`/`sdLineupId`, then updates
 *   the parent's channel state via `onChanged` exactly like
 *   `ChannelMappingForm`'s submit does.
 * - Reject is purely local: it hides that suggestion from this list via
 *   component state. Nothing is persisted - suggestions are always
 *   recomputed fresh the next time "Generate Suggestions" runs, so a
 *   previously-rejected suggestion can legitimately reappear later; that's
 *   expected, not a bug to work around (see CLAUDE.md's Core workflow #4).
 */
export function ChannelSuggestions({ lineupId, channel, onChanged }: ChannelSuggestionsProps) {
  const [rejectedKeys, setRejectedKeys] = useState<Set<string>>(new Set());
  const [acceptingKey, setAcceptingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suggestions = channel.mapping?.suggestions ?? [];

  if (channel.mapping?.confirmed || suggestions.length === 0) {
    return null;
  }

  const visible = suggestions.filter((suggestion) => !rejectedKeys.has(suggestionKey(suggestion)));

  if (visible.length === 0) {
    return null;
  }

  async function handleAccept(suggestion: MappingSuggestion) {
    const key = suggestionKey(suggestion);
    setAcceptingKey(key);
    setError(null);
    try {
      const updated = (await setChannelMapping(lineupId, channel.id, {
        sdStationId: suggestion.sdStationId,
        sdLineupId: suggestion.sdLineupId,
        confirmed: true,
      })) as Channel;
      onChanged(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAcceptingKey(null);
    }
  }

  function handleReject(suggestion: MappingSuggestion) {
    setRejectedKeys((prev) => {
      const next = new Set(prev);
      next.add(suggestionKey(suggestion));
      return next;
    });
  }

  return (
    <Wrapper>
      <Label>Suggested matches:</Label>
      <List>
        {visible.map((suggestion) => {
          const key = suggestionKey(suggestion);
          const busy = acceptingKey !== null;
          return (
            <Item key={key}>
              <StatusBadge $tone={confidenceTone(suggestion.score)}>
                {Math.floor(suggestion.score * 100)}%
              </StatusBadge>
              <StationId>
                station {suggestion.sdStationId} ({suggestion.sdLineupId})
              </StationId>
              <Button type="button" disabled={busy} onClick={() => handleAccept(suggestion)}>
                {acceptingKey === key ? 'Accepting...' : 'Accept'}
              </Button>
              <SecondaryButton type="button" disabled={busy} onClick={() => handleReject(suggestion)}>
                Reject
              </SecondaryButton>
            </Item>
          );
        })}
      </List>
      {error && <ErrorText>{error}</ErrorText>}
    </Wrapper>
  );
}

function suggestionKey(suggestion: MappingSuggestion): string {
  return `${suggestion.sdStationId}:${suggestion.sdLineupId}`;
}

/**
 * Mirrors the backend's bulk-accept cutoff so suggestion tones look
 * consistent with what bulk-accept would actually do.
 *
 * Known limitation: this is a hand-maintained copy, not a value fetched
 * from the backend. `BulkAcceptResult.threshold` (see `types/index.ts`)
 * only comes back from the bulk-accept-suggestions response, and this
 * per-channel component has no threshold to read before that endpoint has
 * ever run. If `backend/app/services/suggestions.py`'s
 * `BULK_ACCEPT_THRESHOLD` is retuned, update this constant to match.
 */
const BULK_ACCEPT_THRESHOLD_DISPLAY = 0.92;

/** Reuses `StatusBadge`'s tone system rather than inventing a new one. */
function confidenceTone(score: number): StatusTone {
  if (score >= BULK_ACCEPT_THRESHOLD_DISPLAY) {
    return 'ok';
  }
  if (score >= 0.6) {
    return 'warning';
  }
  return 'pending';
}
