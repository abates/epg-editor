#!/bin/sh
set -eu

storage_dir="${STORAGE_DIR:-/data}"

# NFR-DEP-4: the app runs as a non-root user, so a bind-mounted /data must be writable by it
if ! mkdir -p "$storage_dir" 2>/dev/null || ! [ -w "$storage_dir" ]; then
  echo "error: $storage_dir is not writable by uid $(id -u) (gid $(id -g))." >&2
  echo "Fix the ownership on the host, for example: chown -R $(id -u):$(id -g) <host dir>" >&2
  exit 1
fi

mkdir -p "$storage_dir/sites" "$storage_dir/lineups" "$storage_dir/guides"

if [ -z "${ORIGIN:-}" ] && [ -z "${PROTOCOL_HEADER:-}" ] && [ -z "${HOST_HEADER:-}" ]; then
  echo "warning: ORIGIN is not set, so forms in the web UI will fail the CSRF check." >&2
  echo "Set it to the URL you open in the browser, for example -e ORIGIN=http://nas.local:3000" >&2
fi

exec "$@"
