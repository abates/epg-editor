import { useRef, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { reimportM3u } from '../api/lineups.js';
import type { Lineup, M3UImportResult } from '../types';
import { M3UImportResultPanel } from './M3UImportResultPanel';
import { Button, Card, ErrorText, FileInput, HelperText } from '../styles/primitives';

const Form = styled.form`
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
`;

const ResultCard = styled(Card)`
  margin-top: 12px;
  background: #f4f8f4;
  border-color: #bfe3bf;
`;

type State =
  | { status: 'idle' }
  | { status: 'importing' }
  | { status: 'done'; result: M3UImportResult }
  | { status: 'error'; message: string };

interface ReimportM3uPanelProps {
  lineupId: string;
  onImported: (lineup: Lineup) => void;
  onChannelRemoved: (channelId: string) => void;
}

/**
 * Re-imports an uploaded M3U playlist into an existing `m3u`-sourced lineup
 * (`POST /api/lineups/{lineupId}/import-m3u`), merging by `tvgId`
 * (fallback: channel number) - see `docs/data-model.md`'s `missingSince`
 * notes. Only rendered for `source === "m3u"` lineups by the caller; the
 * backend rejects this for manually-curated lineups with a 400.
 *
 * Mirrors `SyncAndGeneratePanel`'s pattern: a synchronous in-flight ref
 * guards against a double-submit slipping through before the `disabled`
 * attribute's re-render commits, and a one-time result panel is shown
 * after the request completes.
 *
 * On success, `onImported` is called with the full, already-merged lineup
 * from the response - the caller should replace its lineup state with it
 * directly rather than re-fetching.
 */
export function ReimportM3uPanel({
  lineupId,
  onImported,
  onChannelRemoved,
}: ReimportM3uPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<State>({ status: 'idle' });
  const importInFlightRef = useRef(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || importInFlightRef.current) {
      return;
    }
    importInFlightRef.current = true;
    setState({ status: 'importing' });
    try {
      const response = (await reimportM3u(lineupId, file)) as {
        lineup: Lineup;
        result: M3UImportResult;
      };
      onImported(response.lineup);
      setState({ status: 'done', result: response.result });
      setFile(null);
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      importInFlightRef.current = false;
    }
  }

  const importing = state.status === 'importing';

  return (
    <div>
      <Form onSubmit={handleSubmit}>
        <FileInput
          type="file"
          accept=".m3u,.m3u8"
          disabled={importing}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button type="submit" disabled={importing || !file}>
          {importing ? 'Importing...' : 'Re-import M3U'}
        </Button>
      </Form>
      <HelperText>
        Re-parses the uploaded file and merges it into this lineup: matched
        channels&apos; metadata is refreshed in place (confirmed mappings are
        preserved), unmatched entries are added as new channels, and existing
        channels no longer in the file are flagged missing rather than
        deleted - review them below.
      </HelperText>

      {state.status === 'done' && (
        <ResultCard>
          <M3UImportResultPanel
            lineupId={lineupId}
            result={state.result}
            onChannelRemoved={onChannelRemoved}
          />
        </ResultCard>
      )}

      {state.status === 'error' && (
        <ErrorText>Re-import failed: {state.message}</ErrorText>
      )}
    </div>
  );
}
