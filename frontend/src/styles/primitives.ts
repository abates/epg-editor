import styled, { css } from 'styled-components';

// Small set of shared styled-components primitives used across the
// lineup/channel management pages, so forms/buttons/inputs look
// consistent without copy-pasting the same CSS into every page/component
// file (see CLAUDE.md: styled-components is the only styling system).

export const Page = styled.main`
  max-width: 860px;
  margin: 48px auto 96px;
  padding: 0 24px;
  font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
`;

export const SectionTitle = styled.h1`
  font-size: 26px;
  margin: 0 0 16px;
`;

export const SubsectionTitle = styled.h2`
  font-size: 18px;
  margin: 32px 0 12px;
`;

const buttonBase = css`
  font-size: 14px;
  font-weight: 600;
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
`;

export const Button = styled.button`
  ${buttonBase}
  background: #1456b8;
  color: white;

  &:hover:not(:disabled) {
    background: #0f3f8a;
  }
`;

export const SecondaryButton = styled.button`
  ${buttonBase}
  background: white;
  color: #333;
  border-color: #ccc;

  &:hover:not(:disabled) {
    background: #f2f2f2;
  }
`;

export const DangerButton = styled.button`
  ${buttonBase}
  background: white;
  color: #a31515;
  border-color: #e0a3a3;

  &:hover:not(:disabled) {
    background: #fdecec;
  }
`;

export const Input = styled.input`
  font-size: 14px;
  padding: 7px 10px;
  border: 1px solid #ccc;
  border-radius: 6px;

  &:focus {
    outline: 2px solid #1456b8;
    outline-offset: 1px;
  }
`;

export const FileInput = styled.input`
  font-size: 14px;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
`;

export const Label = styled.label`
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #444;
`;

export const CheckboxLabel = styled.label`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #444;
`;

export const FormGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
`;

export const FormActions = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
`;

export const Card = styled.div`
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
`;

export const ErrorText = styled.p`
  color: #a31515;
  font-size: 14px;
  margin: 8px 0;
`;

export const HelperText = styled.p`
  color: #666;
  font-size: 13px;
  margin: 4px 0 0;
`;
