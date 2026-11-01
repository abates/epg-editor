# epg-editor frontend

React + TypeScript app, scaffolded with [Vite](https://vite.dev) and styled
with [styled-components](https://styled-components.com) (the only styling
system used in this project - no Tailwind/CSS Modules). Dependencies are
managed with plain `npm` (`package.json` + `package-lock.json`).

See the repo root [`CLAUDE.md`](../CLAUDE.md) for the architecture decisions
and module layout this app follows, in particular:

- `src/api/` - vanilla JavaScript. The only module that issues HTTP requests
  to the epg-editor backend.
- `src/components/`, `src/pages/` - TypeScript (`.tsx`), styled-components
  for styling.
- `src/types/` - shared TypeScript types mirroring the backend's Pydantic
  models.

## Development

```bash
npm install
npm run dev     # Vite dev server on :5173, proxies /api and /xmltv to
                # the backend dev server on :8080 (see vite.config.ts)
npm run build   # type-check + production build to dist/
npm run lint    # oxlint
```

In production the backend serves the built frontend, the JSON API
(`/api/*`), and generated XMLTV files (`/xmltv/*`) from a single origin, so
the app never needs a configured backend host/port - see `src/api/`.
