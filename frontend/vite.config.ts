import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
//
// In production the backend (FastAPI/uvicorn) serves the built frontend,
// the JSON API, and the generated XMLTV files from a single origin, so the
// app only ever makes relative requests like `/api/health` (see
// `src/api/`). In dev, Vite serves the frontend on its own port, so we
// proxy the reserved backend path prefixes (see CLAUDE.md's "Reserved URL
// path prefixes") to the backend dev server instead of hardcoding a host
// in application code.
const BACKEND_DEV_URL = "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": BACKEND_DEV_URL,
      "/xmltv": BACKEND_DEV_URL,
    },
    host: "0.0.0.0",
  },
});
