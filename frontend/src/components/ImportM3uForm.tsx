import { useRef, useState, type FormEvent } from 'react';
import styled from 'styled-components';
import { importM3u } from '../api/lineups.js';
import type { Lineup, M3UImportResult } from '../types';
import { Button, ErrorText, FileInput, Input } from '../styles/primitives';

const Form = styled.form`
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
`;

interface ImportM3uFormProps {
  onImported: (lineup: Lineup, result: M3UImportResult) => void;
}

/**
 * Creates a brand-new, `m3u`-sourced lineup from an uploaded M3U playlist
 * (`POST /api/lineups/import-m3u`) - the import counterpart to
 * `LineupsListPage`'s manual-create form. Every parsed entry becomes a new
 * channel, so there's nothing to review/merge here (that's `ReimportM3uPanel`,
 * for re-importing into an existing `m3u`-sourced lineup) - on success this
 * just hands the created lineup + result up to the caller.
 *
 * `POST /api/lineups/import-m3u` is not idempotent - each call creates a
 * brand-new lineup - so, mirroring `SyncAndGeneratePanel`/
 * `ReimportM3uPanel`, a synchronous in-flight ref guards against a
 * double-submit slipping through before the `disabled` attribute's
 * re-render commits.
 */
export function ImportM3uForm({ onImported }: ImportM3uFormProps) {
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const importInFlightRef = useRef(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName || !file || importInFlightRef.current) {
      return;
    }
    importInFlightRef.current = true;
    setImporting(true);
    setError(null);
    try {
      const response = (await importM3u(trimmedName, file)) as {
        lineup: Lineup;
        result: M3UImportResult;
      };
      setName('');
      setFile(null);
      onImported(response.lineup, response.result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      importInFlightRef.current = false;
      setImporting(false);
    }
  }

  return (
    <div>
      <Form onSubmit={handleSubmit}>
        <Input
          type="text"
          placeholder="New lineup name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={importing}
        />
        <FileInput
          type="file"
          accept=".m3u,.m3u8"
          disabled={importing}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button type="submit" disabled={importing || !name.trim() || !file}>
          {importing ? 'Importing...' : 'Import from M3U'}
        </Button>
      </Form>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}
