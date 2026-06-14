-- pgvector observability report (feature-040)
-- Stable column names for dashboards. Run with:
--   docker compose exec -T postgres psql -U estimator -d estimator -f scripts/pgvector_observability.sql
-- Or pipe from host:
--   docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql

\pset format aligned
\pset tuples_only off

WITH vector_columns AS (
    SELECT
        n.nspname AS schema_name,
        c.relname AS table_name,
        a.attname AS column_name,
        t.typname AS type_name,
        CASE
            WHEN t.typname IN ('vector', 'halfvec') AND a.atttypmod > 0 THEN a.atttypmod
            ELSE NULL
        END AS dimensions
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE c.relkind = 'r'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND t.typname IN ('vector', 'halfvec')
),
row_counts AS (
    SELECT
        vc.schema_name,
        vc.table_name,
        vc.column_name,
        vc.dimensions,
        (xpath(
            '/row/cnt/text()',
            query_to_xml(
                format(
                    'SELECT COUNT(*)::bigint AS cnt FROM %I.%I',
                    vc.schema_name,
                    vc.table_name
                ),
                false,
                true,
                ''
            )
        ))[1]::text::bigint AS total_chunks,
        (xpath(
            '/row/cnt/text()',
            query_to_xml(
                format(
                    'SELECT COUNT(%I)::bigint AS cnt FROM %I.%I',
                    vc.column_name,
                    vc.schema_name,
                    vc.table_name
                ),
                false,
                true,
                ''
            )
        ))[1]::text::bigint AS total_vectores
    FROM vector_columns vc
),
vector_indexes AS (
    SELECT
        n.nspname AS schema_name,
        t.relname AS table_name,
        i.relname AS index_name,
        am.amname AS index_method,
        pg_get_indexdef(i.oid) AS index_def,
        pg_relation_size(i.oid) AS index_size_bytes,
        pg_size_pretty(pg_relation_size(i.oid)) AS index_size_pretty,
        (
            SELECT opc.opcname
            FROM unnest(ix.indclass) WITH ORDINALITY AS ic(opc_oid, ord)
            JOIN pg_opclass opc ON opc.oid = ic.opc_oid
            LIMIT 1
        ) AS operator_class
    FROM pg_class t
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_index ix ON ix.indrelid = t.oid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_am am ON am.oid = i.relam
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND am.amname IN ('hnsw', 'ivfflat')
)
SELECT
    rc.table_name AS nombre_tabla,
    rc.column_name AS nombre_columna_vector,
    rc.dimensions AS dimensiones,
    rc.total_chunks,
    rc.total_vectores,
    vi.index_name AS nombre_indice,
    vi.index_method AS metodo_indice,
    vi.operator_class,
    vi.index_size_bytes AS tamano_indice_bytes,
    vi.index_size_pretty AS tamano_indice_pretty,
    pg_size_pretty(pg_total_relation_size(format('%I.%I', rc.schema_name, rc.table_name)::regclass)) AS tamano_tabla_pretty,
    COALESCE(psui.idx_scan, 0) AS idx_scan,
    psui.last_idx_scan
FROM row_counts rc
LEFT JOIN vector_indexes vi
    ON vi.schema_name = rc.schema_name
   AND vi.table_name = rc.table_name
LEFT JOIN pg_stat_user_indexes psui
    ON psui.schemaname = rc.schema_name
   AND psui.relname = rc.table_name
   AND psui.indexrelname = vi.index_name
ORDER BY rc.schema_name, rc.table_name, rc.column_name, vi.index_name NULLS LAST;

\echo ''
\echo '--- pg_settings (memory) ---'

SELECT
    name,
    setting,
    unit,
    CASE
        WHEN unit = '8kB' THEN pg_size_pretty(setting::bigint * 8192)
        WHEN unit = 'kB' THEN pg_size_pretty(setting::bigint * 1024)
        ELSE setting || COALESCE(' ' || unit, '')
    END AS readable_value
FROM pg_settings
WHERE name IN ('shared_buffers', 'effective_cache_size', 'work_mem')
ORDER BY name;
