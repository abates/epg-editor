# Test fixtures

- `xmltv.dtd` — vendored copy of the official XMLTV DTD, fetched from
  `https://raw.githubusercontent.com/XMLTV/xmltv/master/xmltv.dtd` on
  2026-10-29 (commit at that URL's `master` at fetch time). Used by
  `tests/services/test_xmltv.py` to validate generated documents actually
  conform to the DTD's structure, not just that they're well-formed XML.
  Re-fetch and replace if the upstream DTD changes.
