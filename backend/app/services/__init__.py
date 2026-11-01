"""Business logic: M3U parsing, mapping suggestions, XMLTV generation.

Calls into `app.sd_client` and `app.storage`; never performs its own HTTP
requests or raw filesystem I/O (see CLAUDE.md's backend module layout).
"""
