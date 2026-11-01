#!/bin/sh
# Belt-and-suspenders bootstrap for the data volume. app.storage's
# ensure_data_dirs() already does this on FastAPI startup (see
# app/main.py's lifespan), but creating the tree here too means a fresh,
# empty bind mount is guaranteed to have the right layout even before the
# app process gets a chance to run. Honors EPG_EDITOR_DATA_DIR (same env var
# backend/app/storage/paths.py reads) so a non-default data dir doesn't end
# up with only half its tree created.
set -eu

data_dir="${EPG_EDITOR_DATA_DIR:-/data}"
mkdir -p "$data_dir/config" "$data_dir/cache" "$data_dir/output"

exec "$@"
