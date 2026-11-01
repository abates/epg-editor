import { createGlobalStyle } from 'styled-components';

// styled-components is the only styling system in this app (see
// CLAUDE.md) - including base/reset rules, which live here instead of a
// plain CSS file.
export const GlobalStyle = createGlobalStyle`
  :root {
    color-scheme: light dark;
  }

  * {
    box-sizing: border-box;
  }

  body {
    margin: 0;
    font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
  }
`;
