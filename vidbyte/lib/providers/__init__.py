"""Context Protocol Header

Description:
    Database-backed session store providers.
Purpose:
    Exposes Mongo/Supabase/Postgres session stores behind one import surface. Each
    store imports its driver lazily, so importing this package needs no DB driver.
Architecture:
    - ProviderSessionStore: shared serialization base.
    - MongoDbSessionStore / SupabaseSessionStore / PostgresSessionStore: adapters.
Relations:
    Implement vidbyte.sessions.store.SessionStore via ProviderSessionStore.
"""

from __future__ import annotations

from vidbyte.lib.providers.base import ProviderSessionStore
from vidbyte.lib.providers.mongodb import MongoDbSessionStore
from vidbyte.lib.providers.postgres import PostgresSessionStore
from vidbyte.lib.providers.supabase import SupabaseSessionStore

__all__ = [
    "ProviderSessionStore",
    "MongoDbSessionStore",
    "PostgresSessionStore",
    "SupabaseSessionStore",
]
