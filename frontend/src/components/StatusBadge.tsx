import styled from 'styled-components';

export type StatusTone = 'pending' | 'ok' | 'error' | 'warning';

const toneColors: Record<StatusTone, { bg: string; fg: string }> = {
  pending: { bg: '#e5e4e7', fg: '#3f3a46' },
  ok: { bg: '#d8f5d8', fg: '#145214' },
  error: { bg: '#fbd7d7', fg: '#7a1313' },
  warning: { bg: '#fdf0cd', fg: '#7a5a00' },
};

export const StatusBadge = styled.span<{ $tone: StatusTone }>`
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  background: ${({ $tone }) => toneColors[$tone].bg};
  color: ${({ $tone }) => toneColors[$tone].fg};
`;
