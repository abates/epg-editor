"""Shared Pydantic models.

Both epg-editor's own domain objects (Lineup, Channel, ChannelMapping) and
the SchedulesDirect request/response schemas used by `app.sd_client` live
here, so other modules import shapes from a single place.
"""
