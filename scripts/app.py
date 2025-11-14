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
st.title("Diligent — DB Explorer & Join Builder (Analytics & Live Charts)")

# session id
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
SESSION_ID = st.session_state.session_id

# ensure DB exists (auto-generate if missing)
if not DB_PATH.exists():
    try:
        import runpy
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "data_gen.py"))
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ingest_sqlite.py"))
    except Exception as e:
        st.error(f"DB not found and auto-generation failed: {e}")
        st.stop()

# connection (allow thread sharing)
@st.cache_resource
def get_conn(path):
    return sqlite3.connect(str(path), check_same_thread=False)

conn = get_conn(DB_PATH)

# ensure analytics table exists
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

def log_operation(conn, session_id, op_type, op_params, row_count, duration_s):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analytics (ts, session_id, op_type, op_params, row_count, duration_s) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), session_id, op_type, json.dumps(op_params), row_count, duration_s)
    )
    conn.commit()

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

page = st.sidebar.radio("Go to", ["Explorer", "Analytics"])

if page == "Explorer":
    st.write("Build joins, preview tables, run SQL and generate live charts from the join result (all columns available for analytics).")

    st.sidebar.header("Table & Preview")
    left_table = st.sidebar.selectbox("Left table", tables, index=0)
    right_table = st.sidebar.selectbox("Right table", tables, index=min(1, len(tables)-1))

    st.sidebar.write("---")
    st.sidebar.subheader("Preview")
    preview_table = st.sidebar.selectbox("Choose table to preview", ["None"] + tables, index=0)
    preview_rows = st.sidebar.number_input("Rows to preview", min_value=5, max_value=2000, value=10, step=5)

    st.header("Visual Join Builder")
    col1, col2 = st.columns([2,1])

    with col1:
        st.subheader("Select columns to include (for display)")
        left_cols = st.multiselect(f"Columns from {left_table}", options=get_columns(left_table), default=get_columns(left_table))
        right_cols = st.multiselect(f"Columns from {right_table}", options=get_columns(right_table), default=[])

    with col2:
        st.subheader("Join keys & type")
        left_key = st.selectbox(f"Left key ({left_table})", options=get_columns(left_table))
        right_key = st.selectbox(f"Right key ({right_table})", options=get_columns(right_table))
        join_type = st.selectbox("Join type", options=["inner", "left", "right", "outer"], index=0)
        max_rows = st.number_input("Max rows to display (for join)", min_value=10, max_value=5000, value=200, step=10)

    run_join = st.button("Run Join")

    if preview_table != "None":
        st.sidebar.write(f"Previewing **{preview_table}** (first {preview_rows} rows)")
        st.sidebar.dataframe(load_table(preview_table, nrows=preview_rows))

    st.markdown("---")

    if run_join:
        t0 = time.time()
        try:
            # Build display columns and also load full tables for analytics
            left_select = list(dict.fromkeys([left_key] + left_cols))
            right_select = list(dict.fromkeys([right_key] + right_cols))

            # Selected small tables for display
            df_left_display = pd.read_sql_query(f"SELECT {', '.join(left_select)} FROM {left_table}", conn)
            df_right_display = pd.read_sql_query(f"SELECT {', '.join(right_select)} FROM {right_table}", conn)

            # Full tables for analytics
            df_left_full = pd.read_sql_query(f"SELECT * FROM {left_table}", conn)
            df_right_full = pd.read_sql_query(f"SELECT * FROM {right_table}", conn)

            how_map = {"inner":"inner","left":"left","right":"right","outer":"outer"}

            # Full merged DF (for analytics)
            merged_full = pd.merge(df_left_full, df_right_full, left_on=left_key, right_on=right_key, how=how_map[join_type], suffixes=('_L','_R'))

            # Build display dataframe from full merged but only with requested columns (preserve join keys)
            display_cols = []
            for c in [left_key] + left_cols:
                if c not in display_cols:
                    display_cols.append(c)
            for c in [right_key] + right_cols:
                if c not in display_cols:
                    display_cols.append(c)
            # ensure display_cols exist in merged_full (in case of suffixes)
            display_cols = [c for c in display_cols if c in merged_full.columns]

            merged_display = merged_full[display_cols].copy()

            duration = time.time() - t0
            row_count = len(merged_full)

            # log join
            params = {
                "left_table": left_table, "right_table": right_table,
                "left_key": left_key, "right_key": right_key, "join_type": join_type,
                "left_cols": left_select, "right_cols": right_select
            }
            log_operation(conn, SESSION_ID, "join", params, row_count, duration)

            # save to session
            st.session_state["last_merged_full"] = merged_full
            st.session_state["last_merged"] = merged_display

            # show results and analytics controls side by side
            left_col, right_col = st.columns([3,2])
            with left_col:
                st.success(f"Join completed — {row_count} rows (took {duration:.2f}s)")
                st.dataframe(merged_display.head(int(max_rows)), use_container_width=True)
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
                                st.warning("No numeric column selected for histogram.")
                            else:
                                st.bar_chart(df[y_col].value_counts().head(int(chart_limit)))
                                duration_chart = time.time() - t1
                                chart_params = {"chart_type": chart_type, "y_col": y_col}
                                log_operation(conn, SESSION_ID, "chart", chart_params, len(df), duration_chart)
                    except Exception as e:
                        st.error(f"Error generating chart: {e}")

        except Exception as e:
            st.error(f"Error running join: {e}")

    else:
        # show last result if exists
        if "last_merged" in st.session_state:
            merged_display = st.session_state["last_merged"]
            merged_full = st.session_state.get("last_merged_full", merged_display)
            left_col, right_col = st.columns([3,2])
            with left_col:
                st.info("Showing last join result.")
                st.dataframe(merged_display.head(int(max_rows if 'max_rows' in locals() else 50)), use_container_width=True)
            with right_col:
                st.subheader("Live Analytics (on full merged result)")
                cols = merged_full.columns.tolist()
                numeric_cols = merged_full.select_dtypes(include=["number"]).columns.tolist()
                chart_type = st.selectbox("Chart type", options=["bar (aggregated)","line (time series)","pie (aggregated)","histogram"], index=0, key="ct_last")
                x_col = st.selectbox("X column", options=cols, index=0, key="x_last")
                y_col = st.selectbox("Y column (numeric)", options=(numeric_cols if numeric_cols else cols), index=(0 if numeric_cols else 0), key="y_last")
                agg_func = st.selectbox("Aggregation", options=["sum","mean","count"], index=0, key="agg_last")
                chart_limit = st.number_input("Max categories to show", min_value=5, max_value=200, value=20, step=1, key="limit_last")
                show_chart = st.button("Show Analytics (last)")

                if show_chart:
                    try:
                        t1 = time.time()
                        df = merged_full.copy()
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
                                st.warning("No numeric column selected for histogram.")
                            else:
                                st.bar_chart(df[y_col].value_counts().head(int(chart_limit)))
                                duration_chart = time.time() - t1
                                chart_params = {"chart_type": chart_type, "y_col": y_col}
                                log_operation(conn, SESSION_ID, "chart", chart_params, len(df), duration_chart)
                    except Exception as e:
                        st.error(f"Error generating chart: {e}")

    st.markdown("---")
    st.caption("Charts are generated from the full merged result (all columns available).")

else:
    st.header("Analytics — Operations Log & Insights")
    df_analytics = pd.read_sql_query("SELECT * FROM analytics ORDER BY ts DESC LIMIT 10000;", conn)
    if df_analytics.empty:
        st.info("No analytics recorded yet. Run some joins or SQL queries first.")
        st.stop()

    def parse_params(j):
        try:
            o = json.loads(j)
            return json.dumps(o, indent=1)
        except:
            return j

    df_analytics["ts"] = pd.to_datetime(df_analytics["ts"])
    df_analytics["op_params_pretty"] = df_analytics["op_params"].apply(parse_params)

    total_ops = len(df_analytics)
    total_joins = (df_analytics["op_type"] == "join").sum()
    total_sql = (df_analytics["op_type"] == "sql").sum()
    total_charts = (df_analytics["op_type"] == "chart").sum()
    total_rows = df_analytics["row_count"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total operations", total_ops)
    k2.metric("Join operations", total_joins)
    k3.metric("SQL queries", total_sql)
    k4.metric("Charts generated", int(total_charts))

    st.markdown("---")
    st.subheader("Recent operations")
    st.dataframe(df_analytics[["id", "ts", "session_id", "op_type", "row_count", "duration_s", "op_params_pretty"]].head(200), use_container_width=True)

    st.markdown("---")
    st.subheader("Operations over time (by day)")
    df_time = df_analytics.copy()
    df_time["day"] = df_time["ts"].dt.date
    daily = df_time.groupby(["day", "op_type"]).size().unstack(fill_value=0)
    st.line_chart(daily)

    st.markdown("---")
    st.subheader("Top operations by count")
    op_counts = df_analytics.groupby(["op_type"]).size().reset_index(name="count")
    st.bar_chart(op_counts.set_index("op_type"))

    st.markdown("---")
    st.subheader("Filter & export")
    types = ["all"] + sorted(df_analytics["op_type"].unique().tolist())
    sel_type = st.selectbox("Operation type", types, index=0)
    if sel_type == "all":
        filtered = df_analytics
    else:
        filtered = df_analytics[df_analytics["op_type"] == sel_type]

    min_date = df_analytics["ts"].min().date()
    max_date = df_analytics["ts"].max().date()
    dr = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start, end = dr
        filtered = filtered[(filtered["ts"].dt.date >= start) & (filtered["ts"].dt.date <= end)]

    st.write(f"Filtered rows: {len(filtered)}")
    st.dataframe(filtered[["id","ts","session_id","op_type","row_count","duration_s","op_params_pretty"]].head(500), use_container_width=True)
    st.download_button("Download analytics CSV", filtered.to_csv(index=False), file_name="analytics_export.csv", mime="text/csv")
