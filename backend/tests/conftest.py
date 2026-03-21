from __future__ import annotations

"""
Shared test fixtures.

Provides a test database, async sessions, and a configured FastAPI test client.
For parser tests that don't need a database, these fixtures are available
but not required — pytest only injects fixtures that are requested.
"""
