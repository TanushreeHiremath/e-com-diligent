# scripts/app.py
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import json
import time
import uuid
from datetime import datetime

# ---------- CONFIG ----------
REPO_ROOT = Path(__file__).resolve().parents[1]
DB_DIR = REPO_ROOT / "data"
DB_PATH = DB_DIR / "ecom.db"

st.set_page_config(page_title="Diligent DB — Multi-table Join Builder", layout="wide")
st.title("Diligent — Multi-table Join Builder & Live Analytics")

# session id
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
SESSION_ID = st.session_state.session_id

# Auto-generate DB if missing
if not DB_PATH.exists():
    try:
        import runpy
        runpy.run_path(str(REPO_ROOT / "scripts" / "data_gen.py"))
        runpy.run_path(str(REPO_ROOT / "scripts" / "ingest_sqlite.py"))
    except Exception as e:
        st.error(f"Database missing and auto-generation failed: {e}")
        st.stop()

# DB connection (allow thread sharing)
@st.cache_resource
def get_conn(path):
    return sqlite3.connect(str(path), check_same_thread=False)

conn = get_conn(DB_PATH)

# Ensure analytics table exists
def ensure_analytics_table(c):
    c.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        session_id TEXT,
        op_type TEXT,
        op_params TEXT,
        row_count INTEGER,
        duration_s REAL
    );
    """)
    c.commit()

ensure_analytics_table(conn)

def log_operation(conn, session_id, op_type, op_params, row_count, duration_s):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analytics (ts, session_id, op_type, op_params, row_count, duration_s) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), session_id, op_type, json.dumps(op_params), row_count, duration_s)
    )
    conn.commit()

# Utilities
@st.cache_data
def list_tables():
    q = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    return pd.read_sql_query(q, conn)["name"].tolist()

@st.cache_data
def get_columns(table):
    if not table:
        return []
    df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 0", conn)
    return df.columns.tolist()

@st.cache_data
def load_sample(table, nrows=20):
    return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {nrows}", conn)

tables = list_tables()
if not tables:
    st.error("No tables found in DB. Run ingestion script first.")
    st.stop()

# ----------------- Layout -----------------
page = st.sidebar.radio("Go to", ["Join Builder", "SQL Console", "Analytics"])

if page == "Join Builder":
    st.write("Select any tables, set order, pick columns & join keys. The app will run a multi-step join in that order.")

    # 1) choose tables
    selected_tables = st.multiselect("Pick tables to join (choose 2+)", options=tables, default=None, help="Select at least two tables")

    if not selected_tables or len(selected_tables) < 2:
        st.info("Select at least two tables from the sidebar multiselect to enable the multi-table join builder.")
        st.stop()

    # 2) choose order (explicit): build ordered_tables by letting user pick remaining tables one by one
    st.subheader("Arrange join order")
    remaining = selected_tables.copy()
    ordered = []
    for i in range(len(selected_tables)):
        choice = st.selectbox(f"Order position {i+1}", options=remaining, key=f"order_{i}")
        ordered.append(choice)
        remaining = [t for t in remaining if t != choice]

    ordered_tables = ordered

    # 3) show column selectors for each selected table
    st.subheader("Pick columns to include from each table (display only)")
    columns_by_table = {}
    for tbl in ordered_tables:
        cols = get_columns(tbl)
        columns_by_table[tbl] = st.multiselect(f"Columns from {tbl}", options=cols, default=cols, key=f"cols_{tbl}")

    # 4) join key selectors for each consecutive pair
    st.subheader("Define join keys and types for each step")
    join_steps = []
    for i in range(len(ordered_tables)-1):
        left = ordered_tables[i]
        right = ordered_tables[i+1]
        st.markdown(f"**Step {i+1}:** join **{left}** → **{right}**")
        left_key = st.selectbox(f"Left key ({left})", options=get_columns(left), key=f"lk_{i}")
        right_key = st.selectbox(f"Right key ({right})", options=get_columns(right), key=f"rk_{i}")
        join_type = st.selectbox(f"Join type for step {i+1}", options=["inner","left","right","outer"], index=0, key=f"jt_{i}")
        join_steps.append((left, right, left_key, right_key, join_type))

    # optional preview section
    st.markdown("---")
    st.write("Preview small samples of selected tables:")
    preview_cols = st.number_input("Rows to preview per table", min_value=3, max_value=200, value=5, step=1)
    for tbl in ordered_tables:
        st.write(f"**{tbl}** sample")
        st.dataframe(load_sample(tbl, nrows=preview_cols))

    # run join
    run_join = st.button("Run Multi-table Join")

    if run_join:
        t0 = time.time()
        try:
            # load full tables (for analytics) and selected subsets (for display)
            full_dfs = {tbl: pd.read_sql_query(f"SELECT * FROM {tbl}", conn) for tbl in ordered_tables}
            display_dfs = {tbl: pd.read_sql_query(f"SELECT {', '.join(columns_by_table[tbl])} FROM {tbl}", conn) if columns_by_table[tbl] else pd.read_sql_query(f"SELECT * FROM {tbl} LIMIT 0", conn) for tbl in ordered_tables}

            # perform chained merges using join_steps order
            merged_full = full_dfs[ordered_tables[0]]
            for (left, right, left_key, right_key, join_type) in join_steps:
                right_df = full_dfs[right]
                how_map = {"inner":"inner","left":"left","right":"right","outer":"outer"}
                merged_full = pd.merge(merged_full, right_df, left_on=left_key, right_on=right_key, how=how_map[join_type], suffixes=('_L','_R'))

            # build display df: start from merged_full but pick only columns user requested (ensure keys included)
            display_cols = []
            for tbl in ordered_tables:
                # include the join keys if present
                # for safety, include any of the chosen columns that exist in merged_full
                for c in ([c for c in columns_by_table[tbl]] or []):
                    if c in merged_full.columns and c not in display_cols:
                        display_cols.append(c)
            # ensure at least some cols; fallback to all
            if not display_cols:
                merged_display = merged_full.copy()
            else:
                # some columns may have been suffixed after merge; keep any exact matches and suffix variants
                final_display_cols = [c for c in display_cols if c in merged_full.columns]
                merged_display = merged_full[final_display_cols].copy()

            duration = time.time() - t0
            row_count = len(merged_full)

            # save to session state for analytics and charting
            st.session_state["last_merged_full"] = merged_full
            st.session_state["last_merged"] = merged_display

            # log the join operation
            params = {
                "ordered_tables": ordered_tables,
                "join_steps": [{"left":a,"right":b,"left_key":lk,"right_key":rk,"join_type":jt} for (a,b,lk,rk,jt) in join_steps],
                "display_columns": columns_by_table
            }
            log_operation(conn, SESSION_ID, "join", params, row_count, duration)

            # show results and analytics controls
            left_col, right_col = st.columns([3,2])
            with left_col:
                st.success(f"Join completed — {row_count} rows (took {duration:.2f}s)")
                st.dataframe(merged_display.head(250), use_container_width=True)

            with right_col:
                st.subheader("Live Analytics (on full merged result)")
                full_df = st.session_state["last_merged_full"]
                cols = full_df.columns.tolist()
                numeric_cols = full_df.select_dtypes(include=["number"]).columns.tolist()

                chart_type = st.selectbox("Chart type", options=["bar (aggregated)","line (time series)","pie (aggregated)","histogram"], index=0)
                x_col = st.selectbox("X column", options=cols, index=0)
                y_col = st.selectbox("Y column (numeric)", options=(numeric_cols if numeric_cols else cols), index=(0 if numeric_cols else 0))
                agg_func = st.selectbox("Aggregation", options=["sum","mean","count"], index=0)
                chart_limit = st.number_input("Max categories to show", min_value=5, max_value=200, value=20, step=1)
                show_chart = st.button("Show Analytics")

                if show_chart:
                    try:
                        t1 = time.time()
                        df = full_df.copy()
                        if chart_type.startswith("bar") or chart_type.startswith("pie"):
                            if y_col is None:
                                st.warning("No numeric column selected for Y.")
                            else:
                                if agg_func == "sum":
                                    agg = df.groupby(x_col)[y_col].sum().reset_index()
                                elif agg_func == "mean":
                                    agg = df.groupby(x_col)[y_col].mean().reset_index()
                                else:
                                    agg = df.groupby(x_col)[y_col].count().reset_index(name=y_col)
                                agg = agg.sort_values(by=agg.columns[1], ascending=False).head(int(chart_limit))
                                st.dataframe(agg, use_container_width=True)
                                st.bar_chart(agg.set_index(x_col))
                                duration_chart = time.time() - t1
                                chart_params = {"chart_type": chart_type, "x_col": x_col, "y_col": y_col, "agg": agg_func}
                                log_operation(conn, SESSION_ID, "chart", chart_params, int(agg.iloc[:,1].sum() if not agg.empty else 0), duration_chart)
                        elif chart_type.startswith("line"):
                            try:
                                df[x_col] = pd.to_datetime(df[x_col])
                                ts = df.groupby(x_col)[y_col].sum().reset_index().sort_values(by=x_col)
                                st.line_chart(ts.set_index(x_col))
                                duration_chart = time.time() - t1
                                chart_params = {"chart_type": chart_type, "x_col": x_col, "y_col": y_col}
                                log_operation(conn, SESSION_ID, "chart", chart_params, len(ts), duration_chart)
                            except Exception:
                                st.error("Unable to parse X column as datetime for time series.")
                        elif chart_type.startswith("hist"):
                            if y_col is None:
                                st.warning("No numeric column available for histogram.")
                            else:
                                st.bar_chart(df[y_col].value_counts().head(int(chart_limit)))
                                duration_chart = time.time() - t1
                                chart_params = {"chart_type": chart_type, "y_col": y_col}
                                log_operation(conn, SESSION_ID, "chart", chart_params, len(df), duration_chart)
                    except Exception as e:
                        st.error(f"Error generating chart: {e}")

        except Exception as e:
            st.error(f"Error running multi-table join: {e}")

elif page == "SQL Console":
    st.write("Run read-only SELECT queries against the DB.")
    sql = st.text_area("SQL", value="SELECT * FROM orders LIMIT 50;", height=200)
    run = st.button("Run SQL")
    if run:
        if not sql.strip().lower().startswith("select"):
            st.warning("Only SELECT statements allowed here.")
        else:
            t0 = time.time()
            try:
                df_sql = pd.read_sql_query(sql, conn)
                duration = time.time() - t0
                st.write(f"Returned {len(df_sql)} rows (took {duration:.2f}s)")
                st.dataframe(df_sql.head(250), use_container_width=True)
                st.download_button("Download SQL result", df_sql.to_csv(index=False), file_name="sql_result.csv", mime="text/csv")
                log_operation(conn, SESSION_ID, "sql", {"sql": sql}, len(df_sql), duration)
            except Exception as e:
                st.error(f"SQL error: {e}")

else:  # Analytics page
    st.header("Analytics — Operations Log & Insights")
    df_analytics = pd.read_sql_query("SELECT * FROM analytics ORDER BY ts DESC LIMIT 10000;", conn)
    if df_analytics.empty:
        st.info("No analytics recorded yet.")
        st.stop()

    def parse_params(j):
        try:
            return json.dumps(json.loads(j), indent=1)
        except:
            return j

    df_analytics["ts"] = pd.to_datetime(df_analytics["ts"])
    df_analytics["op_params_pretty"] = df_analytics["op_params"].apply(parse_params)

    total_ops = len(df_analytics)
    total_joins = (df_analytics["op_type"] == "join").sum()
    total_sql = (df_analytics["op_type"] == "sql").sum()
    total_charts = (df_analytics["op_type"] == "chart").sum()
    total_rows = df_analytics["row_count"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total ops", total_ops)
    c2.metric("Joins", total_joins)
    c3.metric("SQL", total_sql)
    c4.metric("Charts", int(total_charts))

    st.markdown("---")
    st.subheader("Recent operations")
    st.dataframe(df_analytics[["id","ts","session_id","op_type","row_count","duration_s","op_params_pretty"]].head(500), use_container_width=True)

    st.markdown("---")
    st.subheader("Ops over time")
    df_time = df_analytics.copy()
    df_time["day"] = df_time["ts"].dt.date
    daily = df_time.groupby(["day","op_type"]).size().unstack(fill_value=0)
    st.line_chart(daily)

    st.markdown("---")
    st.subheader("Filter & export")
    types = ["all"] + sorted(df_analytics["op_type"].unique().tolist())
    sel = st.selectbox("Type", types, index=0)
    if sel == "all":
        filtered = df_analytics
    else:
        filtered = df_analytics[df_analytics["op_type"] == sel]

    mn = df_analytics["ts"].min().date()
    mx = df_analytics["ts"].max().date()
    dr = st.date_input("Date range", value=(mn, mx), min_value=mn, max_value=mx)
    if isinstance(dr, (list,tuple)) and len(dr) == 2:
        s,e = dr
        filtered = filtered[(filtered["ts"].dt.date >= s) & (filtered["ts"].dt.date <= e)]

    st.write(f"Filtered rows: {len(filtered)}")
    st.dataframe(filtered[["id","ts","session_id","op_type","row_count","duration_s","op_params_pretty"]].head(500), use_container_width=True)
    st.download_button("Download analytics CSV", filtered.to_csv(index=False), file_name="analytics_export.csv", mime="text/csv")
