"""SchedulesDirect JSON API client.

The only module that makes HTTP calls to SchedulesDirect.org. Exposes a
typed client (token fetch, account lineups, lineup stations, schedules,
programs, logos) built on Pydantic request/response models from
`app.models`. Knows nothing about epg-editor's own domain concepts.
"""
