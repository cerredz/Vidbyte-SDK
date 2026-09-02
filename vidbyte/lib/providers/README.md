# Session-store Provider References

## Scope

| Provider | Official driver or platform documentation | Persistence reference |
| --- | --- | --- |
| MongoDB | [Drivers](https://www.mongodb.com/docs/drivers/) | [Indexes](https://www.mongodb.com/docs/manual/indexes/) |
| PostgreSQL | [Current documentation](https://www.postgresql.org/docs/current/) | [Psycopg 3 documentation](https://www.psycopg.org/psycopg3/docs/) |
| SQLite | [SQLite documentation](https://sqlite.org/docs.html) | [SQL language reference](https://sqlite.org/lang.html) |
| Supabase | [Python client reference](https://supabase.com/docs/reference/python/introduction) | [Database overview](https://supabase.com/docs/guides/database/overview) |

Retrieved 2026-08-29. These links cover the external connection, table,
collection, index, and SQL contracts that a session store must honor. They do
not imply that an optional driver is installed or that a database has already
been provisioned.

## Expanded Provider Reading Maps

The session stores are intentionally thin, but persistence behavior is defined
by the database and driver beneath them. Keep these maps near the store family
so connection, transaction, indexing, migration, and operational assumptions
can be checked before changing a store implementation. **Retrieved:**
2026-08-29.

### MongoDB / Motor

- [MongoDB manual](https://www.mongodb.com/docs/manual/)
- [MongoDB documentation index](https://www.mongodb.com/docs/llms.txt)
- [MongoDB drivers](https://www.mongodb.com/docs/drivers/)
- [PyMongo Python driver](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/)
- [Motor documentation](https://motor.readthedocs.io/en/stable/)
- [Async MongoDB tutorial](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/tutorial/)
- [Connection string reference](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Atlas](https://www.mongodb.com/docs/atlas/)
- [Insert documents](https://www.mongodb.com/docs/manual/tutorial/insert-documents/)
- [Query documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [Update documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [Delete documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/)
- [Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [Index types](https://www.mongodb.com/docs/manual/core/indexes/index-types/)
- [Compound indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [Multikey indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [Partial indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-partial/)
- [Unique indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-unique/)
- [TTL indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [Aggregation pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [Read concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Write concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Read preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [Retryable writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [Schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [Data modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [Change streams](https://www.mongodb.com/docs/manual/changeStreams/)

### PostgreSQL / Psycopg

- [PostgreSQL current documentation](https://www.postgresql.org/docs/current/)
- [PostgreSQL tutorial](https://www.postgresql.org/docs/current/tutorial.html)
- [SQL language](https://www.postgresql.org/docs/current/sql.html)
- [Psycopg 3 documentation](https://www.psycopg.org/psycopg3/docs/)
- [Psycopg async operations](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Psycopg connection pool](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
- [Psycopg row factories](https://www.psycopg.org/psycopg3/docs/api/rows.html)
- [Client authentication](https://www.postgresql.org/docs/current/client-auth.html)
- [Database connection control](https://www.postgresql.org/docs/current/manage-ag-overview.html)
- [libpq connection strings](https://www.postgresql.org/docs/current/libpq-connect.html)
- [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html)
- [Concurrency control](https://www.postgresql.org/docs/current/mvcc.html)
- [Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [Index types](https://www.postgresql.org/docs/current/indexes-types.html)
- [EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
- [Performance tips](https://www.postgresql.org/docs/current/performance-tips.html)
- [JSON types](https://www.postgresql.org/docs/current/datatype-json.html)
- [Full-text search](https://www.postgresql.org/docs/current/textsearch.html)
- [Arrays](https://www.postgresql.org/docs/current/arrays.html)
- [Common table expressions](https://www.postgresql.org/docs/current/queries-with.html)
- [Window functions](https://www.postgresql.org/docs/current/tutorial-window.html)
- [Table partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Roles and privileges](https://www.postgresql.org/docs/current/user-manag.html)
- [Row security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [SSL/TLS support](https://www.postgresql.org/docs/current/ssl-tcp.html)
- [Backup and restore](https://www.postgresql.org/docs/current/backup.html)

### SQLite

- [SQLite documentation](https://sqlite.org/docs.html)
- [SQLite SQL language](https://sqlite.org/lang.html)
- [SQLite home](https://sqlite.org/)
- [C-language interface](https://sqlite.org/c3ref/intro.html)
- [SQLite limits](https://sqlite.org/limits.html)
- [Datatypes](https://sqlite.org/datatype3.html)
- [Foreign key support](https://sqlite.org/foreignkeys.html)
- [CREATE INDEX](https://sqlite.org/lang_createindex.html)
- [Partial indexes](https://sqlite.org/partialindex.html)
- [Indexes on expressions](https://sqlite.org/expridx.html)
- [Generated columns](https://sqlite.org/gencol.html)
- [Transactions](https://sqlite.org/lang_transaction.html)
- [Write-ahead logging](https://sqlite.org/wal.html)
- [Isolation](https://sqlite.org/isolation.html)
- [Locking and concurrency](https://sqlite.org/lockingv3.html)
- [Query planner](https://sqlite.org/queryplanner.html)
- [EXPLAIN QUERY PLAN](https://sqlite.org/eqp.html)
- [Date and time functions](https://sqlite.org/lang_datefunc.html)
- [JSON functions](https://sqlite.org/json1.html)
- [FTS5 full-text search](https://sqlite.org/fts5.html)
- [UPSERT](https://sqlite.org/lang_upsert.html)
- [Online backup API](https://sqlite.org/backup.html)
- [VACUUM](https://sqlite.org/lang_vacuum.html)
- [PRAGMA statements](https://sqlite.org/pragma.html)
- [Threading mode](https://sqlite.org/threadsafe.html)
- [Runtime limits](https://sqlite.org/c3ref/c_limit_attached.html)

### Supabase

- [Supabase documentation](https://supabase.com/docs)
- [Database overview](https://supabase.com/docs/guides/database/overview)
- [Python client reference](https://supabase.com/docs/reference/python/introduction)
- [JavaScript client reference](https://supabase.com/docs/reference/javascript/introduction)
- [Database quickstart](https://supabase.com/docs/guides/database/overview)
- [Connect to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [Database functions](https://supabase.com/docs/guides/database/functions)
- [Database webhooks](https://supabase.com/docs/guides/database/webhooks)
- [Database triggers](https://supabase.com/docs/guides/database/postgres/triggers)
- [Row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Postgres extensions](https://supabase.com/docs/guides/database/extensions)
- [pgvector](https://supabase.com/docs/guides/ai/vector-columns)
- [Connection pooling](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooling)
- [Read replicas](https://supabase.com/docs/guides/platform/read-replicas)
- [Point-in-time recovery](https://supabase.com/docs/guides/platform/backups)
- [Database branching](https://supabase.com/docs/guides/deployment/branching)
- [Local development](https://supabase.com/docs/guides/local-development)
- [Supabase CLI](https://supabase.com/docs/guides/cli)
- [Auth overview](https://supabase.com/docs/guides/auth)
- [Auth server-side](https://supabase.com/docs/guides/auth/server-side)
- [OAuth providers](https://supabase.com/docs/guides/auth/social-login)
- [Storage overview](https://supabase.com/docs/guides/storage)
- [Realtime overview](https://supabase.com/docs/guides/realtime)
- [Edge Functions](https://supabase.com/docs/guides/functions)
- [API keys](https://supabase.com/docs/guides/api/api-keys)
- [Log drains and observability](https://supabase.com/docs/guides/telemetry)
