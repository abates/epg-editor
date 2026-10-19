# syntax=docker/dockerfile:1

# Same base as iptv-org/epg's image [NFR-DEP-1]
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json .npmrc ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine
# git clones iptv-org/epg at runtime; tzdata makes TZ work for cron and display; tini reaps the
# detached "Grab now" / "Sync now" runs; su-exec drops root to PUID/PGID in the entrypoint
RUN apk add --no-cache git tzdata tini su-exec \
  && npm config set --global update-notifier false
WORKDIR /app
# The commands (run:all, run:sync) run from source with tsx, so src/ and the tsconfig chain
# ship next to the SvelteKit build
COPY --from=build /app/package.json /app/package-lock.json /app/.npmrc /app/tsconfig.json ./
COPY --from=build /app/.svelte-kit/tsconfig.json .svelte-kit/tsconfig.json
COPY --from=build /app/node_modules node_modules
COPY --from=build /app/build build
COPY --from=build /app/src src
COPY pm2.config.cjs docker-entrypoint.sh ./

ENV NODE_ENV=production \
    PATH=/app/node_modules/.bin:$PATH \
    PORT=3000 \
    STORAGE_DIR=/data \
    BODY_SIZE_LIMIT=5M \
    EPG_REPO=https://github.com/iptv-org/epg.git \
    EPG_BRANCH=master \
    CRON_SCHEDULE="0 0 * * *" \
    RUN_AT_STARTUP=true \
    TZ=UTC

# NFR-DEP-4: starts as root so the entrypoint can remap the "node" user to PUID/PGID (default
# 1000), then runs everything as "node". A new named volume is seeded with this ownership.
RUN mkdir -p /data && chown node:node /data
VOLUME /data
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD wget -q --spider "http://127.0.0.1:${PORT}/" || exit 1

ENTRYPOINT ["/sbin/tini", "--", "./docker-entrypoint.sh"]
CMD ["pm2-runtime", "pm2.config.cjs"]
