# scripts/app.py
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import json
import time
import uuid
from datetime import datetime

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ecom.db"

st.set_page_config(page_title="Diligent DB Explorer", layout="wide")
st.title("Diligent — DB Explorer & Join Builder (with Analytics)")

# Session id (persist for the streamlit session)
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

SESSION_ID = st.session_state.session_id

# Ensure DB exists (optional auto-create behavior)
if not DB_PATH.exists():
    # If missing, attempt to generate CSVs and DB
    try:
        import runpy
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "data_gen.py"))
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ingest_sqlite.py"))
    except Exception as e:
        st.error(f"DB not found and auto-generation failed: {e}")
        st.stop()

# Create connection; allow cross-thread usage for Streamlit
@st.cache_resource
def get_conn(path):
    return sqlite3.connect(str(path), check_same_thread=False)

conn = get_conn(DB_PATH)

# Create analytics table if not exists
def ensure_analytics_table(c):
    create_sql = """
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        session_id TEXT,
        op_type TEXT,
        op_params TEXT,
        row_count INTEGER,
        duration_s REAL
    );
    """
    c.execute(create_sql)
    c.commit()

ensure_analytics_table(conn)

# Logging helper
def log_operation(conn, session_id, op_type, op_params, row_count, duration_s):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analytics (ts, session_id, op_type, op_params, row_count, duration_s) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), session_id, op_type, json.dumps(op_params), row_count, duration_s)
    )
    conn.commit()

# Utility functions (cached)
@st.cache_data
def list_tables():
    q = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    return pd.read_sql_query(q, conn)["name"].tolist()

@st.cache_data
def get_columns(table):
    if table is None:
        return []
    df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 0", conn)
    return df.columns.tolist()

@st.cache_data
def load_table(table, nrows=1000):
    return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {nrows}", conn)

tables = list_tables()
if not tables:
    st.error("No tables found in the DB. Run ingestion script first.")
    st.stop()

# Sidebar navigation
page = st.sidebar.radio("Go to", ["Explorer", "Analytics"])

# Explorer view
if page == "Explorer":
    st.write("Pick tables/columns, build a join visually, preview and export. You can also run raw SQL.")

    # Sidebar controls for Explorer (kept minimal on main page)
    st.sidebar.header("Table & Preview")
    left_table = st.sidebar.selectbox("Left table", tables, index=0)
    right_table = st.sidebar.selectbox("Right table", tables, index=min(1, len(tables)-1))

    st.sidebar.write("---")
    st.sidebar.subheader("Preview")
    preview_table = st.sidebar.selectbox("Choose table to preview", ["None"] + tables, index=0)
    preview_rows = st.sidebar.number_input("Rows to preview", min_value=5, max_value=2000, value=10, step=5)

    # Join builder
    st.header("Visual Join Builder")
    col1, col2 = st.columns([2,1])

    with col1:
        st.subheader("Select columns to include")
        left_cols = st.multiselect(f"Columns from {left_table}", options=get_columns(left_table), default=get_columns(left_table))
        right_cols = st.multiselect(f"Columns from {right_table}", options=get_columns(right_table), default=[])
        st.caption("Select which columns you want included from each table. Duplicates will be handled automatically.")

    with col2:
        st.subheader("Join keys & type")
        left_key = st.selectbox(f"Left key ({left_table})", options=get_columns(left_table))
        right_key = st.selectbox(f"Right key ({right_table})", options=get_columns(right_table))
        join_type = st.selectbox("Join type", options=["inner", "left", "right", "outer"], index=0)
        max_rows = st.number_input("Max rows to display (for join)", min_value=10, max_value=5000, value=200, step=10)

    run_join = st.button("Run Join")

    # Results area
    st.markdown("---")
    res_area, export_area = st.columns([3,1])

    if preview_table != "None":
        st.sidebar.write(f"Previewing **{preview_table}** (first {preview_rows} rows)")
        st.sidebar.dataframe(load_table(preview_table, nrows=preview_rows))

    if run_join:
        t0 = time.time()
        try:
            # Load selected columns (ensure keys are present)
            left_select = list(dict.fromkeys([left_key] + left_cols))  # ensure left_key included and preserve order
            right_select = list(dict.fromkeys([right_key] + right_cols))

            # Use SQL to limit fetched columns (better for large tables)
            left_sql = f"SELECT {', '.join(left_select)} FROM {left_table}"
            right_sql = f"SELECT {', '.join(right_select)} FROM {right_table}"

            df_left = pd.read_sql_query(left_sql, conn)
            df_right = pd.read_sql_query(right_sql, conn)

            how_map = {"inner": "inner", "left": "left", "right": "right", "outer": "outer"}
            merged = pd.merge(df_left, df_right, left_on=left_key, right_on=right_key, how=how_map[join_type], suffixes=('_L','_R'))

            duration = time.time() - t0
            row_count = len(merged)

            # Log the join operation
            params = {
                "left_table": left_table,
                "right_table": right_table,
                "left_key": left_key,
                "right_key": right_key,
                "join_type": join_type,
                "left_cols": left_select,
                "right_cols": right_select
            }
            log_operation(conn, SESSION_ID, "join", params, row_count, duration)

            st.success(f"Join completed — {row_count} rows (took {duration:.2f}s)")
            res_area.dataframe(merged.head(int(max_rows)), use_container_width=True)

            # Export button
            csv = merged.to_csv(index=False)
            export_area.download_button("Download join CSV", csv, file_name="join_result.csv", mime="text/csv")
        except Exception as e:
            st.error(f"Error running join: {e}")

    # Raw SQL runner
    st.markdown("---")
    st.header("SQL Console (run arbitrary queries)")
    st.caption("Run read-only SELECT queries. Avoid destructive statements here.")
    sql = st.text_area("SQL", value="SELECT * FROM orders LIMIT 50;", height=160)
    run_sql = st.button("Run SQL")

    if run_sql:
        t0 = time.time()
        try:
            if not sql.strip().lower().startswith("select"):
                st.warning("Only SELECT statements are allowed in this console. To run other statements, use the scripts.")
            else:
                df_sql = pd.read_sql_query(sql, conn)
                duration = time.time() - t0
                row_count = len(df_sql)
                # Log SQL operation
                params = {"sql": sql}
                log_operation(conn, SESSION_ID, "sql", params, row_count, duration)

                st.write(f"Query returned {row_count} rows (took {duration:.2f}s).")
                st.dataframe(df_sql, use_container_width=True)
                st.download_button("Download SQL result", df_sql.to_csv(index=False), file_name="sql_result.csv", mime="text/csv")
        except Exception as e:
            st.error(f"SQL error: {e}")

# Analytics view
else:
    st.header("Analytics — Operations Log & Insights")
    st.write("This dashboard shows analytics for joins and SQL queries performed from the app.")

    # Load analytics table into DataFrame
    df_analytics = pd.read_sql_query("SELECT * FROM analytics ORDER BY ts DESC LIMIT 10000;", conn)
    if df_analytics.empty:
        st.info("No analytics recorded yet. Run some joins or SQL queries first.")
        st.stop()

    # parse JSON params column for display
    def parse_params(j):
        try:
            o = json.loads(j)
            return json.dumps(o, indent=1)
        except:
            return j

    df_analytics["ts"] = pd.to_datetime(df_analytics["ts"])
    df_analytics["op_params_pretty"] = df_analytics["op_params"].apply(parse_params)

    # Top KPIs
    total_ops = len(df_analytics)
    total_joins = (df_analytics["op_type"] == "join").sum()
    total_sql = (df_analytics["op_type"] == "sql").sum()
    total_rows = df_analytics["row_count"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total operations", total_ops)
    k2.metric("Join operations", total_joins)
    k3.metric("SQL queries", total_sql)
    k4.metric("Rows returned (total)", int(total_rows))

    st.markdown("---")
    # Recent operations table
    st.subheader("Recent operations")
    st.dataframe(df_analytics[["id", "ts", "session_id", "op_type", "row_count", "duration_s", "op_params_pretty"]].head(200), use_container_width=True)

    st.markdown("---")
    # Operations over time
    st.subheader("Operations over time (by day)")
    df_time = df_analytics.copy()
    df_time["day"] = df_time["ts"].dt.date
    daily = df_time.groupby(["day", "op_type"]).size().unstack(fill_value=0)
    st.line_chart(daily)

    st.markdown("---")
    # Top operations (by count) - show most common param combos
    st.subheader("Top operations by count")
    op_counts = df_analytics.groupby(["op_type"]).size().reset_index(name="count")
    st.bar_chart(op_counts.set_index("op_type"))

    st.markdown("---")
    # Filter & download analytics CSV
    st.subheader("Filter & export")
    types = ["all"] + sorted(df_analytics["op_type"].unique().tolist())
    sel_type = st.selectbox("Operation type", types, index=0)
    if sel_type == "all":
        filtered = df_analytics
    else:
        filtered = df_analytics[df_analytics["op_type"] == sel_type]

    # date range filter
    min_date = df_analytics["ts"].min().date()
    max_date = df_analytics["ts"].max().date()
    dr = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start, end = dr
        filtered = filtered[(filtered["ts"].dt.date >= start) & (filtered["ts"].dt.date <= end)]

    st.write(f"Filtered rows: {len(filtered)}")
    st.dataframe(filtered[["id","ts","session_id","op_type","row_count","duration_s","op_params_pretty"]].head(500), use_container_width=True)
    st.download_button("Download analytics CSV", filtered.to_csv(index=False), file_name="analytics_export.csv", mime="text/csv")

    st.markdown("---")
    st.caption("Analytics are stored in the local SQLite DB (data/ecom.db). If you deploy to a shared host, consider centralizing analytics in a server DB and adding authentication.")
