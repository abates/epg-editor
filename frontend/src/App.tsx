import { useState } from 'react';
import styled from 'styled-components';
import { GlobalStyle } from './styles/GlobalStyle';
import { HealthCheckPage } from './pages/HealthCheckPage';
import { LineupsListPage } from './pages/LineupsListPage';
import { LineupDetailPage } from './pages/LineupDetailPage';
import { SdAccountPage } from './pages/SdAccountPage';

const Nav = styled.nav`
  display: flex;
  gap: 4px;
  padding: 12px 24px;
  border-bottom: 1px solid #ddd;
  font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
`;

const NavButton = styled.button<{ $active: boolean }>`
  background: none;
  border: none;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  color: ${({ $active }) => ($active ? '#1456b8' : '#444')};
  background: ${({ $active }) => ($active ? '#eef2fb' : 'transparent')};

  &:hover {
    background: #eef2fb;
  }
`;

type Section = 'lineups' | 'sd-account' | 'health';

/**
 * Top-level navigation. There's no router dependency decision locked in
 * yet (see CLAUDE.md), and at this scope - three top-level sections, plus a
 * lineups-list/lineup-detail toggle - plain local state is enough; a
 * router would be adding a dependency for navigation this app doesn't
 * structurally need yet.
 */
function App() {
  const [section, setSection] = useState<Section>('lineups');
  const [selectedLineupId, setSelectedLineupId] = useState<string | null>(null);

  function goToLineups() {
    setSection('lineups');
    setSelectedLineupId(null);
  }

  return (
    <>
      <GlobalStyle />
      <Nav>
        <NavButton type="button" $active={section === 'lineups'} onClick={goToLineups}>
          Lineups
        </NavButton>
        <NavButton
          type="button"
          $active={section === 'sd-account'}
          onClick={() => setSection('sd-account')}
        >
          SD account
        </NavButton>
        <NavButton
          type="button"
          $active={section === 'health'}
          onClick={() => setSection('health')}
        >
          Backend health
        </NavButton>
      </Nav>

      {section === 'health' && <HealthCheckPage />}
      {section === 'sd-account' && <SdAccountPage />}
      {section === 'lineups' &&
        (selectedLineupId ? (
          <LineupDetailPage
            lineupId={selectedLineupId}
            onBack={() => setSelectedLineupId(null)}
          />
        ) : (
          <LineupsListPage onSelectLineup={setSelectedLineupId} />
        ))}
    </>
  );
}

export default App;
