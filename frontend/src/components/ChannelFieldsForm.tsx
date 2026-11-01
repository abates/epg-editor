import { useState, type FormEvent } from 'react';
import {
  Button,
  ErrorText,
  FormActions,
  FormGrid,
  Input,
  Label,
  SecondaryButton,
} from '../styles/primitives';
import type { ChannelFieldValues } from './channelFormValues';

interface ChannelFieldsFormProps {
  initialValues: ChannelFieldValues;
  submitLabel: string;
  onSubmit: (values: ChannelFieldValues) => Promise<void>;
  onCancel?: () => void;
}

/**
 * Shared field set for both "add channel" and "edit channel" - name plus
 * the optional metadata fields from `docs/data-model.md`'s `Channel`
 * shape. No M3U-specific UI here (Phase 2).
 */
export function ChannelFieldsForm({
  initialValues,
  submitLabel,
  onSubmit,
  onCancel,
}: ChannelFieldsFormProps) {
  const [values, setValues] = useState<ChannelFieldValues>(initialValues);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof ChannelFieldValues>(key: K, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!values.name.trim()) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(values);
      setValues(initialValues);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <FormGrid>
        <Label>
          Name
          <Input
            type="text"
            value={values.name}
            onChange={(event) => update('name', event.target.value)}
            disabled={submitting}
            required
          />
        </Label>
        <Label>
          Number
          <Input
            type="text"
            placeholder="7.1"
            value={values.number}
            onChange={(event) => update('number', event.target.value)}
            disabled={submitting}
          />
        </Label>
        <Label>
          Logo URL
          <Input
            type="text"
            placeholder="https://..."
            value={values.logoUrl}
            onChange={(event) => update('logoUrl', event.target.value)}
            disabled={submitting}
          />
        </Label>
        <Label>
          tvg-id
          <Input
            type="text"
            placeholder="KGO.us"
            value={values.tvgId}
            onChange={(event) => update('tvgId', event.target.value)}
            disabled={submitting}
          />
        </Label>
        <Label>
          Source stream URL
          <Input
            type="text"
            placeholder="http://hdhomerun.local/auto/v7.1"
            value={values.sourceStreamUrl}
            onChange={(event) => update('sourceStreamUrl', event.target.value)}
            disabled={submitting}
          />
        </Label>
      </FormGrid>
      <FormActions>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving...' : submitLabel}
        </Button>
        {onCancel && (
          <SecondaryButton type="button" disabled={submitting} onClick={onCancel}>
            Cancel
          </SecondaryButton>
        )}
      </FormActions>
      {error && <ErrorText>{error}</ErrorText>}
    </form>
  );
}
