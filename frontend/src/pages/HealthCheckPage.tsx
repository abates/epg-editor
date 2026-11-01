import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { getHealth } from '../api/health.js';
import { StatusBadge, type StatusTone } from '../components/StatusBadge';

const Page = styled.main`
  max-width: 640px;
  margin: 64px auto;
  padding: 0 24px;
  font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
`;

const Title = styled.h1`
  font-size: 28px;
  margin-bottom: 16px;
`;

const Row = styled.p`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
`;

type HealthState =
  | { status: 'loading' }
  | { status: 'ok'; body: unknown }
  | { status: 'error'; message: string };

/**
 * Placeholder scaffolding page: calls the backend's GET /api/health on
 * mount via the vanilla-JS api/ client and renders the result. Real
 * lineup/channel/mapping UI lands in later backlog phases.
 */
export function HealthCheckPage() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((body) => {
        if (!cancelled) {
          setHealth({ status: 'ok', body });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHealth({
            status: 'error',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const tone: StatusTone =
    health.status === 'ok' ? 'ok' : health.status === 'error' ? 'error' : 'pending';

  return (
    <Page>
      <Title>epg-editor</Title>
      <Row>
        Backend status: <StatusBadge $tone={tone}>{describe(health)}</StatusBadge>
      </Row>
      {health.status === 'ok' && (
        <pre>{JSON.stringify(health.body, null, 2)}</pre>
      )}
    </Page>
  );
}

function describe(health: HealthState): string {
  switch (health.status) {
    case 'loading':
      return 'checking...';
    case 'ok':
      return 'ok';
    case 'error':
      return `error: ${health.message}`;
  }
}
