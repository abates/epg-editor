"""Filesystem access under the data directory.

The only module that reads/writes `/data` (configurable via
`EPG_EDITOR_DATA_DIR`): `config/lineups.json`, `cache/sd/*`, and
`output/*.xml`. Responsible for the atomic-write guarantee on
`config/lineups.json` (see docs/data-model.md).
"""
