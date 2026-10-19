#!/bin/sh
set -eu

# NFR-DEP-4: started as root, remap the "node" user to PUID/PGID (default 1000, the image's own
# ids) and re-run this script as that user. Started with --user, there is nothing to remap.
if [ "$(id -u)" = 0 ]; then
  puid="${PUID:-1000}"
  pgid="${PGID:-1000}"
  case "$puid$pgid" in
    '' | *[!0-9]*)
      echo "error: PUID and PGID must be numeric ids (got PUID=$puid PGID=$pgid)." >&2
      exit 1
      ;;
  esac

  if [ "$(id -u node)" != "$puid" ] || [ "$(id -g node)" != "$pgid" ]; then
    sed -i "s/^node:x:[0-9]*:[0-9]*:/node:x:$puid:$pgid:/" /etc/passwd
    sed -i "s/^node:x:[0-9]*:/node:x:$pgid:/" /etc/group
    chown -R node:node /home/node
  fi

  exec su-exec node "$0" "$@"
fi

if [ -n "${PUID:-}${PGID:-}" ] && [ "${PUID:-$(id -u)}:${PGID:-$(id -g)}" != "$(id -u):$(id -g)" ]; then
  echo "warning: PUID/PGID are ignored because the container was started as uid $(id -u)." >&2
fi

storage_dir="${STORAGE_DIR:-/data}"

# The app runs as a non-root user, so a bind-mounted /data must be writable by it
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
