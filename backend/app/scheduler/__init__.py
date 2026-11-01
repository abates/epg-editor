"""APScheduler setup and job definitions.

Jobs are thin: they call into `app.services` functions rather than
embedding business logic themselves.
"""
