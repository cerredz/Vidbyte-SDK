"""Context Protocol Header

Description:
    Database-backed session store providers.
Purpose:
    Exposes SQLite/Mongo/Supabase/Postgres session stores behind one import
    surface. Mongo/Supabase/Postgres import their driver lazily so importing this
    package needs no DB driver; SQLite uses the stdlib sqlite3 module and is safe
    to import anywhere.
Architecture:
    - ProviderSessionStore: shared serialization base.
    - SqliteSessionStore: stdlib sqlite3 adapter (no optional dependency).
    - MongoDbSessionStore / SupabaseSessionStore / PostgresSessionStore: lazy-driver adapters.
Relations:
    Implement vidbyte.sessions.store.SessionStore via ProviderSessionStore.
"""

from __future__ import annotations

from vidbyte.lib.providers.base import ProviderSessionStore
from vidbyte.lib.providers.mongodb import MongoDbSessionStore
from vidbyte.lib.providers.postgres import PostgresSessionStore
from vidbyte.lib.providers.sqlite import SqliteSessionStore
from vidbyte.lib.providers.supabase import SupabaseSessionStore

__all__ = [
    "ProviderSessionStore",
    "MongoDbSessionStore",
    "PostgresSessionStore",
    "SqliteSessionStore",
    "SupabaseSessionStore",
]
