# Spike: overlay symlinks and the epg checkout (M2, FR-O-2, FR-O-3)

- **Date:** 2026-10-18
- **epg:** commit `6f6cfe2` (2026-10-16)

## 1. Symlinked site configs need `NODE_PRESERVE_SYMLINKS=1`

**Result: a plain symlink is not enough.** Node resolves a module's real path before it looks for `node_modules`. A config loaded through `<epg>/sites/<site> -> /data/sites/<site>` runs from `/data/sites/<site>`, so `require('dayjs')` finds no `node_modules` there and the config fails to load.

Checked three ways:

| Setup | Without the variable | With `NODE_PRESERVE_SYMLINKS=1` |
| --- | --- | --- |
| `node` + `import()` of a symlinked CJS config that requires a package | `MODULE_NOT_FOUND` | loads |
| Same under `tsx` (epg runs `grab` with tsx) | `MODULE_NOT_FOUND` | loads, relative `require('./helper')` also works |
| Real `npm run grab --- --channels=sites/local.example/…` in `dev-data/epg`, config does `require('dayjs')` | fails to load the config | `[1/1] local.example … done` |

In the last row the error was `require is not defined in ES module scope`, because the real path was inside this repo (`"type": "module"`). Under `/data/sites` it would be `MODULE_NOT_FOUND`. Either way the config does not load.

**Consequence for M5:** `grabRunner` must spawn `grab` with `NODE_PRESERVE_SYMLINKS=1` in its sanitised env. The guide index does not load configs (it only parses `channels.xml`), so sync is unaffected.

We rejected copying overlay sites into the checkout instead. It would also work, but edits in `/data/sites` would then only take effect after the next sync.

## 2. A fresh epg checkout is not `git status`-clean

iptv-org/epg's `.gitattributes` sets `* text=auto` and `eol=crlf` for `*.js`, `*.ts`, `*.xml`, `*.md`, but many blobs are committed with CRLF. Git reports those files as modified right after a checkout: 1,330 in a plain `git clone`, 333 after our `reset --hard`. They are phantom changes from line-ending normalisation and `reset --hard` does not clear them.

**Consequence:** FR-O-3's "`git status` clean after removing links" holds relative to a fresh checkout. `Overlay.remove()` removes every link and restores every shadowed folder; the tests check a clean status against a fixture repo without CRLF blobs. Nothing in sync relies on `git status` being empty.

## 3. Guide index cost

Parsing every upstream `sites/*/*.channels.xml` with `EPGGrabber.parseChannelsXML`: 538 files, 180,681 entries (149,130 with an empty `xmltv_id`), about 1.5 s and 86 MB of heap on a desktop machine. The web process loads it once and again only after a sync.

`parseChannelsXML` returns partial results for truncated XML instead of throwing. That matches what `grab` would see, so the index does not try to detect it.

## 4. First real sync

`STORAGE_DIR=./dev-data npm run run:sync` with `dev-data/sites/local.example` as the overlay:

```
checked out 6f6cfe2f82fac6bf4e09def36baae4fc5656bacc
found 180682 entries in 252 sites
found 31634 channels and 45244 feeds
sync finished
```

The run took 13.6 s with a warm npm cache. A second sync skipped `npm ci` because the lockfile hash had not changed. A sync started while another held `run.lock` exited with code 1 and the message "another sync or grab is already running".
