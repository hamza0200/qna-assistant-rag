# 8. Databases

## Relational modelling

Model entities as tables, relationships as foreign keys. DocMind: `users 1—N documents 1—N chunks`, `users 1—N conversations 1—N messages`. Choices worth defending:

- **UUID primary keys:** not enumerable in URLs, generated without a DB round trip, merge-friendly. Cost: 16 bytes and random insert order (fragments B-tree pages; UUIDv7 is time-ordered and avoids that).
- **`ON DELETE CASCADE`** from `documents` to `chunks` and `conversations` to `messages`: deleting a parent can't leave orphans, enforced by the database, not application code.
- **Enums** for `document_status` and `message_role`: invalid values are impossible.
- **`created_at` with `server_default=now()`** and timezone-aware timestamps (`TIMESTAMPTZ`).

## Normalization (and when to break it)

- **1NF:** atomic values, no repeating groups. **2NF:** no partial dependency on part of a composite key. **3NF:** no transitive dependencies — non-key columns depend on "the key, the whole key, and nothing but the key".
- Normalization avoids update anomalies (one fact in one place).
- **Deliberate denormalization in DocMind:** `messages.citations` is JSONB holding filename, page and snippet. It's always read with the message, never queried alone, and must survive if the document is later deleted (history shouldn't change). `documents.chunk_count` is a cached aggregate to avoid `COUNT(*)` on every list request.

## Indexes

| Type | Structure | Good for | DocMind |
|---|---|---|---|
| B-tree (default) | balanced sorted tree | `=`, `<`, `>`, `BETWEEN`, `ORDER BY`, prefix `LIKE 'abc%'` | `users.email` (unique), every foreign key (`documents.user_id`, `chunks.document_id`, …) |
| GIN | inverted index (value → rows) | full-text `tsvector`, JSONB containment `@>`, arrays | (hybrid-search next step) |
| HNSW (pgvector) | proximity graph | approximate nearest neighbour | `chunks.embedding` with `vector_cosine_ops` |
| Hash, BRIN, GiST | — | equality only; huge append-only tables; geometric/range | — |

Rules: index foreign keys (Postgres doesn't do it automatically) and columns in frequent `WHERE`/`ORDER BY`; composite index column order matters (leftmost prefix); every index slows writes and takes space; verify with `EXPLAIN ANALYZE`.

## Transactions and isolation levels

A transaction is **ACID**: Atomic (all or nothing), Consistent (constraints hold), Isolated (concurrent transactions don't see each other's partial work), Durable (committed = survives a crash, via the WAL).

DocMind's key transaction: inserting all chunks **and** setting `status='ready'` commit together (`backend/app/services/ingestion.py`) — a document is never "ready" with half its chunks.

| Level | Prevents | Allows | Notes |
|---|---|---|---|
| Read Committed (**Postgres default**) | dirty reads | non-repeatable reads, phantoms | each statement sees committed data as of its start |
| Repeatable Read | + non-repeatable reads (and phantoms in Postgres) | serialization anomalies (write skew) | snapshot per transaction; may raise serialization errors → retry |
| Serializable | all anomalies | — | as if run one at a time; must retry on failure |

Race conditions are often better solved by constraints than by isolation: DocMind relies on the **unique index** on `users.email` and catches `IntegrityError` → 409, instead of "SELECT then INSERT".

## The N+1 query problem

Loading a list, then issuing one extra query *per item* for related data: 1 query for 50 conversations + 50 queries for their messages. Fixes: eager loading (`selectinload` = one extra `WHERE id IN (...)` query; `joinedload` = a JOIN), or write the join yourself. DocMind's `GET /conversations/{id}` uses `selectinload(Conversation.messages)`. Async SQLAlchemy *forbids* implicit lazy loading, which surfaces N+1 as an error instead of a silent slowdown.

## Connection pooling

Opening a Postgres connection costs a TCP + TLS + auth handshake and a server process (~5–10 MB). A pool keeps connections open and lends them to requests. DocMind: `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True` per process. At scale: total connections = replicas × pool size — Postgres handles hundreds, not thousands, so add **PgBouncer** (transaction pooling) in front.

## Migrations

Schema changes as versioned, reviewable code (Alembic). DocMind's `0001_initial_schema.py` creates the pgvector extension, enum types, tables and indexes; containers run `alembic upgrade head` on start, and CI runs `alembic check` to catch models that drift from migrations. **Zero-downtime migrations** use expand/contract: add nullable column → deploy code that writes both → backfill → switch reads → drop the old column later. Avoid long locks (`CREATE INDEX CONCURRENTLY`, add constraints `NOT VALID` then validate).

## SQL vs NoSQL (Postgres vs MongoDB)

| | PostgreSQL | MongoDB |
|---|---|---|
| Model | tables, fixed schema (+ JSONB for flexible parts) | JSON documents, flexible schema |
| Relationships | joins, foreign keys, constraints | embedding or manual references; `$lookup` |
| Transactions | full ACID, multi-row, mature | multi-document transactions supported, less central |
| Scaling | vertical + read replicas; sharding via Citus/partitioning | built-in horizontal sharding |
| Best for | relational data, integrity, reporting, mixed workloads | document-shaped data, rapidly changing schemas, very high write scale |

DocMind is relational (ownership chains, cascades, joins in the retrieval query) and benefits from pgvector — Postgres is the natural fit.

## JSONB

Binary JSON in Postgres: parsed once on write, indexable with GIN, queryable (`->`, `->>`, `@>` containment, `jsonb_path_query`). Use it for data that's variable in shape and read as a unit (DocMind's citations, settings, API payloads). Don't use it to avoid modelling: things you filter, join or constrain on belong in real columns.
