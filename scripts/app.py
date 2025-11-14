# scripts/app.py
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ecom.db"

st.set_page_config(page_title="Diligent DB Explorer", layout="wide")

st.title("Diligent — DB Explorer & Join Builder")
st.write("Pick tables/columns, build a join visually, preview and export. You can also run raw SQL.")

# Connect to DB (cached). Use check_same_thread=False so Streamlit threads can share it.
@st.cache_resource
def get_conn(path):
    # NOTE: check_same_thread=False allows using the connection across threads.
    # For heavier usage consider creating a new connection per request instead.
    return sqlite3.connect(str(path), check_same_thread=False)

conn = get_conn(DB_PATH)

# Utility functions
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

# Sidebar controls
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
    try:
        # Load selected columns (ensure keys are present)
        left_select = list(dict.fromkeys([left_key] + left_cols))  # ensure left_key included and preserve order
        right_select = list(dict.fromkeys([right_key] + right_cols))

        # Use SQL to limit fetched columns (better for large tables)
        left_sql = f"SELECT {', '.join(left_select)} FROM {left_table}"
        right_sql = f"SELECT {', '.join(right_select)} FROM {right_table}"

        df_left = pd.read_sql_query(left_sql, conn)
        df_right = pd.read_sql_query(right_sql, conn)

        # If column name collision (same name in both), pandas merge will suffix automatically.
        how_map = {"inner": "inner", "left": "left", "right": "right", "outer": "outer"}
        merged = pd.merge(df_left, df_right, left_on=left_key, right_on=right_key, how=how_map[join_type], suffixes=('_L','_R'))

        st.success(f"Join completed — {len(merged)} rows")
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
    try:
        # Basic protection: only allow SELECT statements (simple check)
        if not sql.strip().lower().startswith("select"):
            st.warning("Only SELECT statements are allowed in this console. To run other statements, use the scripts.")
        else:
            df_sql = pd.read_sql_query(sql, conn)
            st.write(f"Query returned {len(df_sql)} rows.")
            st.dataframe(df_sql, use_container_width=True)
            st.download_button("Download SQL result", df_sql.to_csv(index=False), file_name="sql_result.csv", mime="text/csv")
    except Exception as e:
        st.error(f"SQL error: {e}")

st.markdown("---")
st.write("Tips: use the preview panel to inspect tables, choose keys carefully, and limit output to avoid very large datasets.")
