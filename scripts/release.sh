#!/usr/bin/env bash
# Cut a new epg-editor release.
#
# Usage: scripts/release.sh patch|minor|major
#
# - Reads the current version from backend/pyproject.toml (the single
#   source of truth once backend/frontend versions are reconciled — see
#   CLAUDE.md's "Docker" section).
# - Sanity-checks frontend/package.json already matches it; refuses to
#   proceed (and does NOT "fix" the drift for you) if it doesn't, since
#   that indicates something bypassed this script.
# - Bumps the requested semver component, writes both files, regenerates
#   both lockfiles (backend/uv.lock via `uv lock`, frontend/package-lock.json
#   via `npm install --package-lock-only`) so they track the new version,
#   commits, tags, and pushes both the branch and the tag atomically.
#   Pushing the tag is what triggers .github/workflows/release.yml's GHCR
#   publish.
set -euo pipefail

usage() {
  echo "Usage: $0 patch|minor|major" >&2
}

if [ "$#" -ne 1 ]; then
  usage
  exit 1
fi

bump_kind="$1"
case "$bump_kind" in
  patch|minor|major) ;;
  *)
    echo "Error: unknown bump kind '$bump_kind'" >&2
    usage
    exit 1
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

backend_pyproject="backend/pyproject.toml"
frontend_package_json="frontend/package.json"

if [ ! -f "$backend_pyproject" ]; then
  echo "Error: $backend_pyproject not found (run this from within the epg-editor repo)." >&2
  exit 1
fi
if [ ! -f "$frontend_package_json" ]; then
  echo "Error: $frontend_package_json not found (run this from within the epg-editor repo)." >&2
  exit 1
fi

# Working tree must be clean before we start, so the release commit only
# ever contains the two version bumps and nothing incidental.
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is not clean. Commit, stash, or discard your changes before releasing." >&2
  git status --short >&2
  exit 1
fi

# HEAD must be on a real branch (not detached) — we need a branch name to
# push the release commit to.
if ! current_branch="$(git symbolic-ref -q --short HEAD)"; then
  echo "Error: HEAD is detached (not on a branch). Check out the branch you want to release from before running this script." >&2
  exit 1
fi

current_backend_version="$(python3 -c "
import tomllib
with open('$backend_pyproject', 'rb') as f:
    data = tomllib.load(f)
print(data['project']['version'])
")"

current_frontend_version="$(jq -r '.version' "$frontend_package_json")"

if [ -z "$current_backend_version" ] || [ "$current_backend_version" = "null" ]; then
  echo "Error: could not read [project].version from $backend_pyproject." >&2
  exit 1
fi

if [ "$current_backend_version" != "$current_frontend_version" ]; then
  echo "Error: version drift detected." >&2
  echo "  $backend_pyproject reports:    $current_backend_version" >&2
  echo "  $frontend_package_json reports: $current_frontend_version" >&2
  echo "These must match before releasing. Fix the drift by hand (figure out which one is correct and why they diverged) rather than re-running this script — it will not guess for you." >&2
  exit 1
fi

current_version="$current_backend_version"

if ! [[ "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  echo "Error: current version '$current_version' is not a plain X.Y.Z semver triple; this script doesn't know how to bump it." >&2
  exit 1
fi

major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
patch="${BASH_REMATCH[3]}"

case "$bump_kind" in
  major)
    major=$((major + 1))
    minor=0
    patch=0
    ;;
  minor)
    minor=$((minor + 1))
    patch=0
    ;;
  patch)
    patch=$((patch + 1))
    ;;
esac

new_version="${major}.${minor}.${patch}"
tag_name="v${new_version}"

echo "Current version: $current_version"
echo "New version:      $new_version ($bump_kind bump)"

# Fail fast if the tag we're about to create already exists locally — far
# easier to catch here than after the version files are already rewritten
# and committed.
if git rev-parse -q --verify "refs/tags/${tag_name}" >/dev/null; then
  echo "Error: tag '${tag_name}' already exists locally. Delete it (git tag -d ${tag_name}) if it's stale, or investigate why a release for this version already happened." >&2
  exit 1
fi

# Rewrite backend/pyproject.toml's version line in place, leaving
# everything else untouched.
python3 - "$backend_pyproject" "$current_version" "$new_version" <<'PYEOF'
import re
import sys

path, old_version, new_version = sys.argv[1:4]

with open(path, "r") as f:
    content = f.read()

pattern = re.compile(
    r'^(version\s*=\s*")' + re.escape(old_version) + r'(")',
    re.MULTILINE,
)
new_content, count = pattern.subn(r"\g<1>" + new_version + r"\g<2>", content, count=1)
if count != 1:
    print(f"Error: expected to replace exactly one version line in {path}, replaced {count}.", file=sys.stderr)
    sys.exit(1)

with open(path, "w") as f:
    f.write(new_content)
PYEOF

# backend/pyproject.toml's version changed; regenerate backend/uv.lock so
# it tracks the new project version (uv embeds it in the lockfile's own
# entry for the project).
(cd backend && uv lock)

# Rewrite frontend/package.json's "version" field in place, preserving
# key order/formatting via a targeted regex rather than a full
# json.load/dump round-trip (which would reformat the whole file).
python3 - "$frontend_package_json" "$current_version" "$new_version" <<'PYEOF'
import re
import sys

path, old_version, new_version = sys.argv[1:4]

with open(path, "r") as f:
    content = f.read()

pattern = re.compile(
    r'("version"\s*:\s*")' + re.escape(old_version) + r'(")'
)
new_content, count = pattern.subn(r"\g<1>" + new_version + r"\g<2>", content, count=1)
if count != 1:
    print(f"Error: expected to replace exactly one version field in {path}, replaced {count}.", file=sys.stderr)
    sys.exit(1)

with open(path, "w") as f:
    f.write(new_content)
PYEOF

# frontend/package.json's version changed; regenerate
# frontend/package-lock.json so it tracks the new version too (without
# touching node_modules or running install scripts).
(cd frontend && npm install --package-lock-only --ignore-scripts)

backend_uv_lock="backend/uv.lock"
frontend_package_lock="frontend/package-lock.json"

git add "$backend_pyproject" "$frontend_package_json" "$backend_uv_lock" "$frontend_package_lock"
git commit -m "Release v${new_version}"

git tag -a "$tag_name" -m "$tag_name"

# Push the release commit and its tag together, atomically: either both
# land on origin or neither does, so we never end up with a pushed tag
# whose branch commit didn't make it (or vice versa).
if ! git push --atomic origin "$current_branch" "$tag_name"; then
  echo "Error: atomic push of '$current_branch' + '$tag_name' to origin failed." >&2
  echo "Nothing was pushed (that's the point of --atomic), but the commit and tag DO exist locally:" >&2
  git log -1 --oneline >&2
  git tag -l "$tag_name" >&2
  echo "To recover:" >&2
  echo "  - Fix whatever origin rejected (e.g. pull/rebase if origin/$current_branch moved), then retry:" >&2
  echo "      git push --atomic origin $current_branch $tag_name" >&2
  echo "  - Or undo the local release commit and tag and start over:" >&2
  echo "      git tag -d $tag_name && git reset --hard HEAD~1" >&2
  exit 1
fi

echo "Released $tag_name and pushed $current_branch + the tag to origin."
echo "The release workflow (.github/workflows/release.yml) will build and publish ghcr.io/abates/epg-editor:${tag_name} (and move :latest) from here."
