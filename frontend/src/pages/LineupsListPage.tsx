import { useCallback, useEffect, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { createLineup, listLineups } from '../api/lineups.js';
import type { Lineup } from '../types';
import { Button, ErrorText, Input, Page, SectionTitle } from '../styles/primitives';

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
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
`;

const LineupName = styled.button`
  background: none;
  border: none;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  color: #1456b8;
  padding: 0;
  text-align: left;

  &:hover {
    text-decoration: underline;
  }
`;

const Meta = styled.span`
  font-size: 13px;
  color: #666;
`;

const CreateForm = styled.form`
  display: flex;
  gap: 8px;
`;

type ListState =
  | { status: 'loading' }
  | { status: 'ok'; lineups: Lineup[] }
  | { status: 'error'; message: string };

interface LineupsListPageProps {
  onSelectLineup: (lineupId: string) => void;
}

/**
 * Top-level lineups list: shows existing lineups (name links through to
 * the detail view) and a form to create a new, empty, manually-sourced
 * lineup. Importing from M3U lands in a later phase.
 */
export function LineupsListPage({ onSelectLineup }: LineupsListPageProps) {
  const [state, setState] = useState<ListState>({ status: 'loading' });
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Fetches the lineup list and lands it (or any failure) into state,
  // without touching `state` synchronously first - see the mount effect
  // below, which relies on the initial `useState` value for the loading
  // state instead of setting it again itself.
  const load = useCallback(() => {
    (listLineups() as Promise<Lineup[]>)
      .then((lineups) => setState({ status: 'ok', lineups }))
      .catch((error: unknown) =>
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        }),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) {
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createLineup({ name: trimmed });
      setNewName('');
      setState({ status: 'loading' });
      load();
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreating(false);
    }
  }

  return (
    <Page>
      <SectionTitle>Lineups</SectionTitle>

      {state.status === 'loading' && <p>Loading lineups...</p>}
      {state.status === 'error' && (
        <ErrorText>Failed to load lineups: {state.message}</ErrorText>
      )}
      {state.status === 'ok' &&
        (state.lineups.length === 0 ? (
          <p>No lineups yet - create one below.</p>
        ) : (
          <LineupListEl>
            {state.lineups.map((lineup) => (
              <LineupItem key={lineup.id}>
                <LineupName type="button" onClick={() => onSelectLineup(lineup.id)}>
                  {lineup.name}
                </LineupName>
                <Meta>
                  {lineup.channels.length} channel{lineup.channels.length === 1 ? '' : 's'} ·{' '}
                  {lineup.source}
                </Meta>
              </LineupItem>
            ))}
          </LineupListEl>
        ))}

      <CreateForm onSubmit={handleCreate}>
        <Input
          type="text"
          placeholder="New lineup name"
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          disabled={creating}
        />
        <Button type="submit" disabled={creating || !newName.trim()}>
          {creating ? 'Creating...' : 'Create lineup'}
        </Button>
      </CreateForm>
      {createError && <ErrorText>{createError}</ErrorText>}
    </Page>
  );
}
