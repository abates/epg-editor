import { useState, type FormEvent } from 'react';
import { setChannelMapping } from '../api/lineups.js';
import type { Channel } from '../types';
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

interface ChannelMappingFormProps {
  lineupId: string;
  channel: Channel;
  sdLineupIds: string[];
  onSaved: (channel: Channel) => void;
  onCancel: () => void;
}

/**
 * Directly sets a channel's SD station mapping. There's no suggestion
 * scoring yet (Phase 3), so this is plain text-field entry for
 * `sdStationId`/`sdLineupId` rather than a picker.
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

  return (
    <form onSubmit={handleSubmit}>
      <FormGrid>
        <Label>
          SD station id
          <Input
            type="text"
            value={sdStationId}
            onChange={(event) => setSdStationId(event.target.value)}
            disabled={submitting}
            required
          />
        </Label>
        <Label>
          SD lineup id
          <Input
            type="text"
            value={sdLineupId}
            onChange={(event) => setSdLineupId(event.target.value)}
            disabled={submitting}
            required
          />
        </Label>
      </FormGrid>
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
