import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { checkXmltvExists, getXmltvUrl } from '../api/xmltv.js';
import { Card, HelperText, SecondaryButton } from '../styles/primitives';

const UrlRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const UrlText = styled.code`
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
  background: #f4f4f4;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 7px 10px;
`;

const CopiedLabel = styled.span`
  font-size: 13px;
  font-weight: 600;
  color: #1a7a1a;
`;

const NotGeneratedCard = styled(Card)`
  background: #f8f8f8;
  color: #666;
  font-size: 14px;
`;

// How long the transient "Copied!" confirmation stays visible after a
// successful clipboard write, in milliseconds.
const COPIED_LABEL_DURATION_MS = 2000;

type ExistenceState = 'checking' | 'exists' | 'missing';

interface XmltvUrlPanelProps {
  lineupId: string;
}

/** Last `checkXmltvExists` result landed, tagged with which `lineupId` it's for. */
interface ExistenceResult {
  lineupId: string;
  exists: boolean;
}

/**
 * Surfaces the absolute XMLTV URL (`/xmltv/{lineupId}.xml`, using the
 * browser's own origin) a user would point Plex/Jellyfin at, plus a
 * copy-to-clipboard button - so they don't have to hand-construct it
 * (backlog item 35).
 *
 * Only shows the live URL + copy button once a file has actually been
 * generated for this lineup. There's no persisted "generated"/
 * "generatedAt" field on `Lineup` to check directly (see
 * `backend/app/models/lineup.py`), so existence is determined truthfully
 * via a cheap `HEAD` request against the serving endpoint itself
 * (`checkXmltvExists`) rather than inferred from something indirect like
 * "has any mapped channel" - a lineup can have mapped channels without a
 * refresh/generation cycle having run yet. Re-checks whenever
 * `lineupId` changes; does not currently re-check after a background
 * refresh completes elsewhere on the page (e.g. via `RefreshNowPanel`) -
 * a manual page reload picks that up, which is an acceptable gap for a
 * first pass.
 */
export function XmltvUrlPanel({ lineupId }: XmltvUrlPanelProps) {
  // Tagging the result with the `lineupId` it was fetched for (rather than
  // just a bare boolean) lets `existence` below derive the "checking"
  // state during render - from a stale/absent result not matching the
  // current `lineupId` - instead of needing a second, synchronous
  // `setState` call at the top of the effect to reset to "checking" on
  // every `lineupId` change.
  const [result, setResult] = useState<ExistenceResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    checkXmltvExists(lineupId).then((exists) => {
      if (!cancelled) {
        setResult({ lineupId, exists });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [lineupId]);

  const existence: ExistenceState =
    result && result.lineupId === lineupId ? (result.exists ? 'exists' : 'missing') : 'checking';

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = setTimeout(() => setCopied(false), COPIED_LABEL_DURATION_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(getXmltvUrl(lineupId));
      setCopied(true);
    } catch {
      // Clipboard access can be denied (permissions, insecure context,
      // etc.) - silently no-op rather than showing an alarming error for
      // what's a convenience feature; the URL is still visible to copy by
      // hand.
    }
  }

  if (existence === 'checking') {
    return <HelperText>Checking XMLTV status...</HelperText>;
  }

  if (existence === 'missing') {
    return (
      <NotGeneratedCard>
        XMLTV hasn&apos;t been generated for this lineup yet. It&apos;s written by the
        scheduled/manual refresh pipeline once this lineup has mapped channels.
      </NotGeneratedCard>
    );
  }

  return (
    <div>
      <UrlRow>
        <UrlText>{getXmltvUrl(lineupId)}</UrlText>
        <SecondaryButton type="button" onClick={handleCopy}>
          Copy
        </SecondaryButton>
        {copied && <CopiedLabel>Copied!</CopiedLabel>}
      </UrlRow>
      <HelperText>Point Plex/Jellyfin (or any XMLTV-compatible client) at this URL.</HelperText>
    </div>
  );
}
