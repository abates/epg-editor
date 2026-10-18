# Spike: does `lcn` in channels.xml reach the guide? (M1, FR-X-3)

**Result: yes.** iptv-org/epg's `grab` carries the `lcn` attribute from `channels.xml` through to `<lcn>` in the guide. epg's own `channels:lint` XSD also accepts our generated file.

- **Date:** 2026-10-18
- **epg:** commit `6f6cfe2` (2026-10-16), `epg-grabber` 0.48.0

## Setup

1. Shallow-cloned iptv-org/epg, then ran `npm ci --ignore-scripts` and `npm run api:load`.
2. Added a throwaway site, `sites/spike.local/spike.local.config.js`. Its `url()` points at a local HTTP server that returns two canned programmes per `site_id`, so the run needs no network access.
3. Generated `channels.xml` with our `generateChannelsXml()` from `tests/__data__/input/m3u/hdhomerun.m3u`, with three channels mapped. One of them has an empty `xmltv_id`, and its `site_id` contains `&` and `"`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<channels>
  <channel site="spike.local" site_id="wcbs" lang="en" xmltv_id="WCBSTV.us@SD" lcn="2.1">WCBS-HD</channel>
  <channel site="spike.local" site_id="nbc lx &amp; &quot;more&quot;" lang="en" xmltv_id="" lcn="4.10">NBC LX</channel>
  <channel site="spike.local" site_id="wnet" lang="en" xmltv_id="WNETTV.us@SD" lcn="13.1">WNET-HD</channel>
</channels>
```

4. Ran it with a sanitised environment (`env -i PATH HOME`):

```sh
npm run grab --- --channels=<file> --output=<guide.xml> --days=1
```

## Output (channels)

```xml
<channel id="WCBSTV.us@SD"><display-name>WCBS-HD</display-name><lcn>2.1</lcn></channel>
<channel id="nbc lx &amp; &quot;more&quot;"><display-name>NBC LX</display-name><lcn>4.10</lcn></channel>
<channel id="WNETTV.us@SD"><display-name>WNET-HD</display-name><lcn>13.1</lcn></channel>
```

Programmes for all three channels were written with matching `channel` ids.

## Findings

- `lcn` is kept as a string (`4.10` stays `4.10`), and every guide `<channel>` gets an `<lcn>` (FR-X-3).
- `<display-name>` is the text content of the `channels.xml` element, which is the M3U name (FR-X-4).
- An empty `xmltv_id` makes the guide use `site_id` as the channel id. That confirms the CLAUDE.md gotcha, so the UI should warn about it (FR-E-2).
- Escaped `&` and `"` round-trip correctly through `escapeString`, epg-grabber and the guide.
- `npm run channels:lint -- <file>` passes on our file. As a control, a file with an extra attribute (`bogus="y"`) is rejected, so the XSD check is real.
- `grab` needs `temp/data` from `api:load` before it runs, even for a local site (`loading api data...`).

The automated end-to-end version of this check is the opt-in integration test planned for M5 (ARCHITECTURE §8).
