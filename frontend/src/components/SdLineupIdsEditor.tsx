import { useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { updateLineupSdLineups } from '../api/lineups.js';
import type { Lineup } from '../types';
import { Button, ErrorText, HelperText, Input } from '../styles/primitives';

const ChipList = styled.ul`
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

const Chip = styled.li`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 10px;
  border-radius: 999px;
  background: #eef2fb;
  color: #1f2a44;
  font-size: 13px;
  font-family: ui-monospace, monospace;
`;

const RemoveButton = styled.button`
  border: none;
  background: none;
  cursor: pointer;
  color: #666;
  font-size: 14px;
  line-height: 1;
  padding: 0 4px;

  &:hover:not(:disabled) {
    color: #a31515;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
`;

const AddForm = styled.form`
  display: flex;
  gap: 8px;
`;

interface SdLineupIdsEditorProps {
  lineupId: string;
  sdLineupIds: string[];
  onChanged: (sdLineupIds: string[]) => void;
}

/**
 * Raw add/remove editor for a lineup's associated SchedulesDirect lineup
 * ids. There's no SD-account-lineup-browsing UI yet (that's Phase 4), so
 * this is plain text-id entry rather than a picker against the real SD
 * account.
 */
export function SdLineupIdsEditor({ lineupId, sdLineupIds, onChanged }: SdLineupIdsEditorProps) {
  const [newId, setNewId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(nextIds: string[]) {
    setSaving(true);
    setError(null);
    try {
      const updated = (await updateLineupSdLineups(lineupId, nextIds)) as Lineup;
      onChanged(updated.sdLineupIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  function handleAdd(event: FormEvent) {
    event.preventDefault();
    const trimmed = newId.trim();
    if (!trimmed || sdLineupIds.includes(trimmed)) {
      return;
    }
    setNewId('');
    void save([...sdLineupIds, trimmed]);
  }

  function handleRemove(id: string) {
    void save(sdLineupIds.filter((existing) => existing !== id));
  }

  return (
    <div>
      {sdLineupIds.length === 0 ? (
        <HelperText>No SD lineups associated yet.</HelperText>
      ) : (
        <ChipList>
          {sdLineupIds.map((id) => (
            <Chip key={id}>
              {id}
              <RemoveButton
                type="button"
                aria-label={`Remove ${id}`}
                disabled={saving}
                onClick={() => handleRemove(id)}
              >
                &times;
              </RemoveButton>
            </Chip>
          ))}
        </ChipList>
      )}
      <AddForm onSubmit={handleAdd}>
        <Input
          type="text"
          placeholder="SD lineup id (e.g. USA-OTA-12345)"
          value={newId}
          onChange={(event) => setNewId(event.target.value)}
          disabled={saving}
        />
        <Button type="submit" disabled={saving || !newId.trim()}>
          Add
        </Button>
      </AddForm>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}
