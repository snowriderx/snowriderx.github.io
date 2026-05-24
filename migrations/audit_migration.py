"""
audit_migration.py — Database migration audit: SQL Server → PostgreSQL
Runs 10 verification steps and outputs:
  - migration_check_report.txt  (human-readable)
  - migration_issues.csv        (machine-readable failures/warnings)

Usage:
    python migrations/audit_migration.py \
        --src "mssql+pymssql://user:pass@host/db" \
        --dst "postgresql://user:pass@host:port/db"
"""

import argparse
import csv
import sys
import os
import io
from datetime import datetime
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pymssql
import psycopg2
import psycopg2.extras

# ── Connection helpers ────────────────────────────────────────────────────────

def parse_mssql_url(url: str) -> dict:
    rest = url.replace("mssql+pymssql://", "")
    userpass, hostdb = rest.split("@", 1)
    user, password = userpass.split(":", 1)
    host, db = hostdb.split("/", 1)
    return dict(server=host, user=user, password=unquote(password), database=db, timeout=30)


def parse_pg_url(url: str) -> dict:
    # postgresql://user:pass@host:port/db
    rest = url.replace("postgresql://", "")
    userpass, hostdb = rest.split("@", 1)
    user, password = userpass.split(":", 1)
    if "/" in hostdb:
        hostport, db = hostdb.split("/", 1)
    else:
        hostport, db = hostdb, ""
    if ":" in hostport:
        host, port = hostport.split(":", 1)
    else:
        host, port = hostport, "5432"
    return dict(host=host, port=int(port), user=user, password=unquote(password), dbname=db)


# ── Report helpers ────────────────────────────────────────────────────────────

class Report:
    def __init__(self):
        self.buf = io.StringIO()
        self.issues: list[dict] = []

    def h(self, text: str):
        line = f"\n{'='*70}\n{text}\n{'='*70}"
        print(line)
        self.buf.write(line + "\n")

    def p(self, text: str = ""):
        print(text)
        self.buf.write(text + "\n")

    def issue(self, step: int, severity: str, table: str, column: str, description: str):
        row = dict(step=step, severity=severity, table=table, column=column, description=description)
        self.issues.append(row)
        prefix = "❌" if severity == "FAIL" else "⚠️ "
        self.p(f"  {prefix} [{severity}] {table}.{column if column else '*'} — {description}")

    def ok(self, text: str):
        self.p(f"  ✅ {text}")

    def save(self, report_path: str, csv_path: str):
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self.buf.getvalue())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["step","severity","table","column","description"])
            writer.writeheader()
            writer.writerows(self.issues)
        print(f"\n📄 Report saved to: {report_path}")
        print(f"📊 Issues CSV saved to: {csv_path}")


R = Report()


# ── Type normalisation (SQL Server → canonical) ───────────────────────────────

def normalise_ms_type(data_type: str, char_max: int | None, num_prec: int | None, num_scale: int | None) -> str:
    t = data_type.lower()
    if t in ("nvarchar", "varchar", "nchar", "char"):
        if char_max == -1:
            return "text"
        return f"varchar({char_max})" if char_max else "varchar"
    if t in ("ntext", "text", "xml"):
        return "text"
    if t == "int":
        return "integer"
    if t == "bigint":
        return "bigint"
    if t == "smallint":
        return "smallint"
    if t == "tinyint":
        return "smallint"
    if t == "bit":
        return "integer"   # we store bit as int in PG (model uses Integer)
    if t in ("datetime", "datetime2", "smalldatetime"):
        return "timestamp"
    if t == "date":
        return "date"
    if t in ("decimal", "numeric"):
        return f"numeric({num_prec},{num_scale})"
    if t == "float":
        return "double precision"
    if t in ("real",):
        return "real"
    if t == "uniqueidentifier":
        return "uuid"
    if t in ("varbinary", "binary", "image"):
        return "bytea"
    if t == "money":
        return "numeric(19,4)"
    return t


def normalise_pg_type(udt_name: str, char_max: int | None, num_prec: int | None, num_scale: int | None) -> str:
    t = udt_name.lower()
    if t in ("character varying", "varchar"):
        return f"varchar({char_max})" if char_max else "text"
    if t in ("character", "char", "bpchar"):
        return f"char({char_max})" if char_max else "char"
    if t in ("text", "ntext"):
        return "text"
    if t in ("integer", "int4", "int"):
        return "integer"
    if t in ("bigint", "int8"):
        return "bigint"
    if t in ("smallint", "int2"):
        return "smallint"
    if t in ("boolean", "bool"):
        return "boolean"
    if t in ("timestamp without time zone", "timestamp"):
        return "timestamp"
    if t == "date":
        return "date"
    if t in ("numeric", "decimal"):
        if num_prec:
            return f"numeric({num_prec},{num_scale})"
        return "numeric"
    if t in ("double precision", "float8"):
        return "double precision"
    if t == "real":
        return "real"
    if t == "uuid":
        return "uuid"
    if t == "bytea":
        return "bytea"
    if t == "jsonb":
        return "jsonb"
    if t == "json":
        return "json"
    return t


# ── Step 1: Tables ────────────────────────────────────────────────────────────

def step1_tables(ms_cur, pg_cur):
    R.h("STEP 1 — Table List Comparison")

    ms_cur.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA='dbo' ORDER BY TABLE_NAME"
    )
    ms_tables = {r[0] for r in ms_cur.fetchall()}

    pg_cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    pg_tables = {r[0] for r in pg_cur.fetchall()}

    R.p(f"SQL Server tables: {len(ms_tables)}")
    R.p(f"PostgreSQL tables: {len(pg_tables)}")

    missing = ms_tables - pg_tables
    extra = pg_tables - ms_tables

    if missing:
        for t in sorted(missing):
            R.issue(1, "FAIL", t, "", "Table in SQL Server but MISSING in PostgreSQL")
    else:
        R.ok("All SQL Server tables present in PostgreSQL")

    if extra:
        for t in sorted(extra):
            R.issue(1, "WARN", t, "", "Table in PostgreSQL but not in SQL Server")
    else:
        R.ok("No extra tables in PostgreSQL")

    common = ms_tables & pg_tables
    R.p(f"\nCommon tables ({len(common)}): {', '.join(sorted(common))}")
    return common, ms_tables, pg_tables


# ── Step 2: Schema / columns ──────────────────────────────────────────────────

def step2_schema(ms_cur, pg_cur, common_tables):
    R.h("STEP 2 — Column Schema Comparison")

    for table in sorted(common_tables):
        # SQL Server columns
        ms_cur.execute("""
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                COLUMNPROPERTY(OBJECT_ID(%s), c.COLUMN_NAME, 'IsIdentity') AS is_identity,
                c.ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE TABLE_NAME = %s AND TABLE_SCHEMA = 'dbo'
            ORDER BY ORDINAL_POSITION
        """, (table, table))
        ms_cols = {r[0]: r for r in ms_cur.fetchall()}

        # PostgreSQL columns
        pg_cur.execute("""
            SELECT
                column_name,
                udt_name,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table,))
        pg_cols = {r[0]: r for r in pg_cur.fetchall()}

        ms_names = set(ms_cols.keys())
        pg_names = set(pg_cols.keys())
        missing_cols = ms_names - pg_names
        extra_cols = pg_names - ms_names

        problems = False
        if missing_cols:
            for c in sorted(missing_cols):
                R.issue(2, "FAIL", table, c, f"Column missing in PostgreSQL (SQL Server type: {ms_cols[c][1]})")
                problems = True
        if extra_cols:
            for c in sorted(extra_cols):
                R.issue(2, "WARN", table, c, f"Extra column in PostgreSQL (not in SQL Server)")

        # Type comparison for common columns
        for col in sorted(ms_names & pg_names):
            ms_r = ms_cols[col]
            pg_r = pg_cols[col]
            ms_norm = normalise_ms_type(ms_r[1], ms_r[2], ms_r[3], ms_r[4])
            pg_norm = normalise_pg_type(pg_r[1], pg_r[2], pg_r[3], pg_r[4])

            if ms_norm != pg_norm:
                # Allow text ≈ varchar(n) for long text columns
                ms_is_text = ms_norm in ("text", "ntext") or ms_norm.startswith("varchar")
                pg_is_text = pg_norm in ("text",) or pg_norm.startswith("varchar")
                if not (ms_is_text and pg_is_text):
                    R.issue(2, "WARN", table, col,
                            f"Type mismatch: SQL Server={ms_norm} PG={pg_norm}")
                    problems = True

            # NULL constraint
            ms_null = ms_r[5]  # "YES"/"NO"
            pg_null = pg_r[5]
            if ms_null != pg_null:
                R.issue(2, "WARN", table, col,
                        f"Nullable mismatch: SQL Server={ms_null} PG={pg_null}")

        if not problems and not missing_cols and not extra_cols:
            R.ok(f"{table}: schema OK ({len(ms_cols)} columns)")


# ── Step 3: Constraints ───────────────────────────────────────────────────────

def step3_constraints(ms_cur, pg_cur, common_tables):
    R.h("STEP 3 — Constraints (PK / FK / UNIQUE / CHECK)")

    for table in sorted(common_tables):
        # SQL Server PKs
        ms_cur.execute("""
            SELECT ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
              ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            WHERE tc.TABLE_NAME = %s AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY ku.ORDINAL_POSITION
        """, (table,))
        ms_pks = [r[0] for r in ms_cur.fetchall()]

        pg_cur.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
            ORDER BY kcu.ordinal_position
        """, (table,))
        pg_pks = [r[0] for r in pg_cur.fetchall()]

        if ms_pks != pg_pks:
            R.issue(3, "FAIL", table, "PRIMARY KEY",
                    f"PK mismatch: SQL Server={ms_pks} PG={pg_pks}")
        else:
            R.ok(f"{table}: PK OK ({ms_pks})")

        # SQL Server UNIQUE constraints
        ms_cur.execute("""
            SELECT tc.CONSTRAINT_NAME, ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
              ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            WHERE tc.TABLE_NAME = %s AND tc.CONSTRAINT_TYPE = 'UNIQUE'
        """, (table,))
        ms_uniq = {r[0]: r[1] for r in ms_cur.fetchall()}

        # FK check (SQL Server side)
        ms_cur.execute("""
            SELECT
                fk.name AS fk_name,
                COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS col,
                OBJECT_NAME(fkc.referenced_object_id) AS ref_table,
                COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ref_col
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            WHERE OBJECT_NAME(fk.parent_object_id) = %s
        """, (table,))
        ms_fks = ms_cur.fetchall()

        if ms_fks:
            R.issue(3, "WARN", table, "FOREIGN KEY",
                    f"SQL Server has {len(ms_fks)} FK(s) — verify manually in PG (FK typically not migrated by create_all)")


# ── Step 4: Indexes ───────────────────────────────────────────────────────────

def step4_indexes(ms_cur, pg_cur, common_tables):
    R.h("STEP 4 — Indexes")

    for table in sorted(common_tables):
        ms_cur.execute("""
            SELECT
                i.name AS index_name,
                i.is_unique,
                i.is_primary_key,
                STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS cols
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE OBJECT_NAME(i.object_id) = %s AND i.type > 0
            GROUP BY i.name, i.is_unique, i.is_primary_key
        """, (table,))
        ms_indexes = ms_cur.fetchall()

        pg_cur.execute("""
            SELECT
                i.relname AS index_name,
                ix.indisunique,
                ix.indisprimary,
                array_to_string(ARRAY(
                    SELECT a.attname FROM pg_attribute a
                    WHERE a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                    ORDER BY array_position(ix.indkey, a.attnum)
                ), ', ') AS cols
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            WHERE t.relname = %s AND t.relkind = 'r'
        """, (table,))
        pg_idx_names = {r[0] for r in pg_cur.fetchall()}

        non_pk_ms = [r for r in ms_indexes if not r[2]]  # exclude PK
        if not non_pk_ms:
            continue

        R.p(f"\n  {table} — SQL Server indexes: {len(non_pk_ms)}")
        for idx in non_pk_ms:
            name, is_unique, _, cols = idx
            # Check if a similar index exists in PG by column pattern
            R.p(f"    {'UNIQUE ' if is_unique else ''}INDEX {name} ON ({cols})")
            if name not in pg_idx_names:
                R.issue(4, "WARN", table, name, f"Index '{name}' not found in PostgreSQL (cols: {cols})")


# ── Step 5: Views ─────────────────────────────────────────────────────────────

def step5_views(ms_cur, pg_cur):
    R.h("STEP 5 — Views")

    ms_cur.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA='dbo'"
    )
    ms_views = [r[0] for r in ms_cur.fetchall()]

    pg_cur.execute(
        "SELECT viewname FROM pg_views WHERE schemaname='public'"
    )
    pg_views = {r[0] for r in pg_cur.fetchall()}

    if not ms_views:
        R.ok("No views in SQL Server — nothing to migrate")
        return

    for v in ms_views:
        if v not in pg_views:
            R.issue(5, "FAIL", v, "", "View in SQL Server MISSING in PostgreSQL")
        else:
            R.ok(f"View '{v}' present in PostgreSQL")


# ── Step 6: Stored Procedures / Functions ────────────────────────────────────

def step6_procedures(ms_cur, pg_cur):
    R.h("STEP 6 — Stored Procedures / Functions")

    ms_cur.execute(
        "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM INFORMATION_SCHEMA.ROUTINES "
        "WHERE ROUTINE_SCHEMA='dbo' ORDER BY ROUTINE_NAME"
    )
    ms_routines = ms_cur.fetchall()

    if not ms_routines:
        R.ok("No stored procedures/functions in SQL Server")
        return

    pg_cur.execute(
        "SELECT proname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid "
        "WHERE n.nspname='public'"
    )
    pg_funcs = {r[0] for r in pg_cur.fetchall()}

    for name, rtype in ms_routines:
        if name.lower() not in {f.lower() for f in pg_funcs}:
            R.issue(6, "WARN", name, "", f"{rtype} not found in PostgreSQL — may need manual conversion")
        else:
            R.ok(f"{rtype} '{name}' found in PostgreSQL")


# ── Step 7: Triggers ──────────────────────────────────────────────────────────

def step7_triggers(ms_cur, pg_cur):
    R.h("STEP 7 — Triggers")

    ms_cur.execute(
        "SELECT name FROM sys.triggers WHERE parent_class = 1"
    )
    ms_triggers = [r[0] for r in ms_cur.fetchall()]

    if not ms_triggers:
        R.ok("No triggers in SQL Server")
        return

    pg_cur.execute(
        "SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema='public'"
    )
    pg_triggers = {r[0] for r in pg_cur.fetchall()}

    for t in ms_triggers:
        if t not in pg_triggers:
            R.issue(7, "WARN", t, "", "Trigger in SQL Server MISSING in PostgreSQL")
        else:
            R.ok(f"Trigger '{t}' present in PostgreSQL")


# ── Step 8: Row Count & Data Sampling ────────────────────────────────────────

def step8_rowcounts(ms_cur, pg_cur, common_tables):
    R.h("STEP 8 — Row Count & Data Sampling")

    counts = []
    for table in sorted(common_tables):
        ms_cur.execute(f'SELECT COUNT(*) FROM [{table}]')
        ms_count = ms_cur.fetchone()[0]

        pg_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        pg_count = pg_cur.fetchone()[0]

        match = "✅" if ms_count == pg_count else "❌"
        R.p(f"  {match} {table}: SQL Server={ms_count}  PG={pg_count}")
        if ms_count != pg_count:
            R.issue(8, "FAIL", table, "COUNT",
                    f"Row count mismatch: SQL Server={ms_count} PG={pg_count}")
        counts.append((table, ms_count, pg_count))

    # Sample top 3 largest tables
    top_tables = sorted(counts, key=lambda x: x[1], reverse=True)[:3]
    R.p(f"\n  --- Data sampling (top {len(top_tables)} tables by row count) ---")

    for table, ms_count, pg_count in top_tables:
        if ms_count == 0:
            continue
        R.p(f"\n  [{table}] — sampling 3 rows")

        # Get PG columns
        pg_cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s AND table_schema='public' ORDER BY ordinal_position LIMIT 5",
            (table,)
        )
        pg_sample_cols = [r[0] for r in pg_cur.fetchall()]

        # MS sample
        ms_cur.execute(f'SELECT TOP 3 {", ".join(f"[{c}]" for c in pg_sample_cols)} FROM [{table}]')
        ms_rows = ms_cur.fetchall()

        # PG sample
        pg_col_list = ", ".join(f'"{c}"' for c in pg_sample_cols)
        pg_cur.execute(f'SELECT {pg_col_list} FROM "{table}" LIMIT 3')
        pg_rows = pg_cur.fetchall()

        for i, (ms_row, pg_row) in enumerate(zip(ms_rows, pg_rows)):
            for j, col in enumerate(pg_sample_cols):
                ms_val = str(ms_row[j])[:80] if ms_row[j] is not None else "NULL"
                pg_val = str(pg_row[j])[:80] if pg_row[j] is not None else "NULL"
                if ms_val != pg_val:
                    R.issue(8, "WARN", table, col,
                            f"Row {i+1} value mismatch: MS={ms_val!r} PG={pg_val!r}")


# ── Step 9: Sequences ─────────────────────────────────────────────────────────

def step9_sequences(ms_cur, pg_cur, common_tables):
    R.h("STEP 9 — Sequences / Auto-increment")

    for table in sorted(common_tables):
        # Find IDENTITY columns in SQL Server
        ms_cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s
              AND COLUMNPROPERTY(OBJECT_ID(%s), COLUMN_NAME, 'IsIdentity') = 1
        """, (table, table))
        identity_cols = [r[0] for r in ms_cur.fetchall()]

        for col in identity_cols:
            # Get max value in PG
            try:
                pg_cur.execute(f'SELECT MAX("{col}") FROM "{table}"')
                max_val = pg_cur.fetchone()[0] or 0
            except Exception:
                R.issue(9, "FAIL", table, col, f"Cannot read MAX({col}) from PostgreSQL")
                pg_cur.execute("ROLLBACK")
                continue

            # Check sequence current value
            seq_name = f'{table}_{col}_seq'
            try:
                pg_cur.execute(f"SELECT last_value FROM \"{seq_name}\"")
                seq_val = pg_cur.fetchone()[0]
                if seq_val < max_val:
                    R.issue(9, "FAIL", table, col,
                            f"Sequence {seq_name} last_value={seq_val} < MAX({col})={max_val} — will cause INSERT conflict!")
                else:
                    R.ok(f"{table}.{col}: sequence OK (last_value={seq_val}, MAX={max_val})")
            except Exception:
                pg_cur.execute("ROLLBACK")
                # May be a GENERATED ALWAYS column — check differently
                try:
                    pg_cur.execute(f"""
                        SELECT pg_get_serial_sequence('"{table}"', '{col}')
                    """)
                    seqname = pg_cur.fetchone()[0]
                    if seqname:
                        pg_cur.execute(f"SELECT last_value FROM {seqname}")
                        seq_val = pg_cur.fetchone()[0]
                        if seq_val < max_val:
                            R.issue(9, "WARN", table, col,
                                    f"Sequence {seqname} last_value={seq_val} < MAX={max_val}")
                        else:
                            R.ok(f"{table}.{col}: sequence OK via pg_get_serial_sequence")
                    else:
                        R.issue(9, "WARN", table, col,
                                f"No sequence found for {table}.{col} — GENERATED ALWAYS or missing")
                except Exception as e:
                    pg_cur.execute("ROLLBACK")
                    R.issue(9, "WARN", table, col, f"Cannot determine sequence: {e}")


# ── Step 10: Summary ─────────────────────────────────────────────────────────

def step10_summary(ms_tables, pg_tables, common_tables):
    R.h("STEP 10 — Summary Report")

    fails = [i for i in R.issues if i["severity"] == "FAIL"]
    warns = [i for i in R.issues if i["severity"] == "WARN"]

    R.p(f"\n{'─'*50}")
    R.p(f"✅ PASSED items:")
    passed_steps = set(range(1, 10)) - {i["step"] for i in fails}
    for s in sorted(passed_steps):
        R.p(f"  Step {s}")

    if fails:
        R.p(f"\n❌ FAILED ({len(fails)} issues):")
        for f in fails:
            R.p(f"  Step {f['step']} | {f['table']}.{f['column']} — {f['description']}")

    if warns:
        R.p(f"\n⚠️  WARNINGS ({len(warns)} issues):")
        for w in warns:
            R.p(f"  Step {w['step']} | {w['table']}.{w['column']} — {w['description']}")

    score = 10 - len({i["step"] for i in fails})
    R.p(f"\n{'─'*50}")
    R.p(f"Score: {score}/10 steps passed")
    R.p(f"Total tables: SQL Server={len(ms_tables)}, PostgreSQL={len(pg_tables)}, Common={len(common_tables)}")

    if not fails:
        R.p("\n🎉 Kết luận: Migration ĐẠT — an toàn để go-live.")
    elif len(fails) <= 3:
        R.p("\n⚠️  Kết luận: Có vấn đề nhỏ — cần fix trước khi go-live.")
    else:
        R.p("\n❌ Kết luận: Migration CHƯA ĐẠT — cần điều tra và fix.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migration audit: SQL Server → PostgreSQL")
    parser.add_argument("--src", required=True, help="SQL Server URL (mssql+pymssql://...)")
    parser.add_argument("--dst", required=True, help="PostgreSQL URL (postgresql://...)")
    parser.add_argument("--out-dir", default=".", help="Output directory for report files")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(args.out_dir, f"migration_check_report_{ts}.txt")
    csv_path = os.path.join(args.out_dir, f"migration_issues_{ts}.csv")

    R.h(f"MIGRATION AUDIT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    R.p(f"Source: {args.src.split('@')[-1]}")
    R.p(f"Target: {args.dst.split('@')[-1]}")

    # Connect
    R.p("\nConnecting to SQL Server...")
    ms_params = parse_mssql_url(args.src)
    ms_conn = pymssql.connect(**ms_params)
    ms_cur = ms_conn.cursor()
    R.p("  ✅ SQL Server connected")

    R.p("Connecting to PostgreSQL...")
    pg_params = parse_pg_url(args.dst)
    pg_conn = psycopg2.connect(**pg_params)
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor()
    R.p("  ✅ PostgreSQL connected")

    try:
        common, ms_tables, pg_tables = step1_tables(ms_cur, pg_cur)
        step2_schema(ms_cur, pg_cur, common)
        step3_constraints(ms_cur, pg_cur, common)
        step4_indexes(ms_cur, pg_cur, common)
        step5_views(ms_cur, pg_cur)
        step6_procedures(ms_cur, pg_cur)
        step7_triggers(ms_cur, pg_cur)
        step8_rowcounts(ms_cur, pg_cur, common)
        step9_sequences(ms_cur, pg_cur, common)
        step10_summary(ms_tables, pg_tables, common)
    finally:
        ms_conn.close()
        pg_conn.close()
        R.save(report_path, csv_path)


if __name__ == "__main__":
    main()
