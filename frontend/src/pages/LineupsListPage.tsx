import { useCallback, useEffect, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { createLineup, deleteLineup, listLineups } from '../api/lineups.js';
import { ImportM3uForm } from '../components/ImportM3uForm';
import { RefreshNowPanel } from '../components/RefreshNowPanel';
import { UnidentifiedEntriesWarning } from '../components/UnidentifiedEntriesWarning';
import type { Lineup, M3UImportResult } from '../types';
import {
  Button,
  Card,
  DangerButton,
  ErrorText,
  Input,
  Page,
  SecondaryButton,
  SectionTitle,
  SubsectionTitle,
} from '../styles/primitives';

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

const LineupActions = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const CreateForm = styled.form`
  display: flex;
  gap: 8px;
`;

const ImportSummaryCard = styled(Card)`
  margin-top: 12px;
  background: #f4f8f4;
  border-color: #bfe3bf;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
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
 * the detail view), a form to create a new, empty, manually-sourced
 * lineup, a form to create a new `m3u`-sourced lineup by uploading an
 * M3U playlist (`ImportM3uForm`), and the global "Refresh Now" trigger
 * (`RefreshNowPanel`) - this page, not a single lineup's detail page, is
 * where that lives since it runs across every lineup, not just one.
 */
export function LineupsListPage({ onSelectLineup }: LineupsListPageProps) {
  const [state, setState] = useState<ListState>({ status: 'loading' });
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [imported, setImported] = useState<{ lineup: Lineup; result: M3UImportResult } | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  async function handleDelete(lineup: Lineup) {
    const channelCount = lineup.channels.length;
    const confirmed = window.confirm(
      `Delete lineup "${lineup.name}"? This will permanently remove it and all ${channelCount} ` +
        `channel${channelCount === 1 ? '' : 's'} in it, including any confirmed mappings. ` +
        'This cannot be undone.',
    );
    if (!confirmed) {
      return;
    }
    setDeletingId(lineup.id);
    setDeleteError(null);
    try {
      await deleteLineup(lineup.id);
      setState((prev) => {
        if (prev.status !== 'ok') {
          return prev;
        }
        return { status: 'ok', lineups: prev.lineups.filter((item) => item.id !== lineup.id) };
      });
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeletingId(null);
    }
  }

  function handleImported(lineup: Lineup, result: M3UImportResult) {
    setImported({ lineup, result });
    // The response already reflects the created lineup, but refresh the
    // list from the backend too so it's consistent with the rest of this
    // page's load/refresh pattern (e.g. if the user navigates back here
    // later without a full reload).
    setState({ status: 'loading' });
    load();
  }

  return (
    <Page>
      <SectionTitle>Lineups</SectionTitle>

      <SubsectionTitle>Refresh</SubsectionTitle>
      <RefreshNowPanel />

      {state.status === 'loading' && <p>Loading lineups...</p>}
      {state.status === 'error' && (
        <ErrorText>Failed to load lineups: {state.message}</ErrorText>
      )}
      {deleteError && <ErrorText>Failed to delete lineup: {deleteError}</ErrorText>}
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
                <LineupActions>
                  <Meta>
                    {lineup.channels.length} channel{lineup.channels.length === 1 ? '' : 's'} ·{' '}
                    {lineup.source}
                  </Meta>
                  <DangerButton
                    type="button"
                    disabled={deletingId === lineup.id}
                    onClick={() => handleDelete(lineup)}
                  >
                    {deletingId === lineup.id ? 'Deleting...' : 'Delete'}
                  </DangerButton>
                </LineupActions>
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

      <SubsectionTitle>Import from M3U</SubsectionTitle>
      <ImportM3uForm onImported={handleImported} />
      {imported && (
        <>
          <ImportSummaryCard>
            <span>
              Imported {imported.result.added.length} channel
              {imported.result.added.length === 1 ? '' : 's'} into &quot;{imported.lineup.name}
              &quot;.
            </span>
            <SecondaryButton type="button" onClick={() => onSelectLineup(imported.lineup.id)}>
              View lineup &rarr;
            </SecondaryButton>
          </ImportSummaryCard>
          <UnidentifiedEntriesWarning
            unidentifiedEntryCount={imported.result.unidentifiedEntryCount}
          />
        </>
      )}
    </Page>
  );
}
