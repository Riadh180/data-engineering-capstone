#!/usr/bin/env python3
"""app.py — AI x Work capstone dashboard (interactive serving layer)."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()  # read .env so GOLD_BACKEND / PG* are set automatically
except ImportError:
    pass
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

GOLD = os.environ.get("GOLD_DIR", "data/gold")
AI, ASSIST, HUMAN, BUILD = "#F0A202", "#E86A5C", "#6B7A99", "#4C9BE8"
BG, PANEL, TXT, MUTED, GRID = "#0E1117", "#171B24", "#F2F4F8", "#B7BFD0", "#2E3547"
BUCKET_ORDER = ["0-20", "20-100", "100-500", "500+"]

pio.templates["aiwork"] = go.layout.Template(layout=dict(
    paper_bgcolor=BG, plot_bgcolor=BG,
    font=dict(color=TXT, family="Inter, system-ui, sans-serif", size=13),
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor=GRID, title_font=dict(color=MUTED)),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=GRID, title_font=dict(color=MUTED)),
    margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(font_size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=TXT))))

def base(fig, title=None, h=380):
    fig.update_layout(template="aiwork", height=h,
                      margin=dict(l=10, r=10, t=64, b=10),
                      title=dict(text=title, font=dict(size=16),
                                 y=0.97, yanchor="top", x=0.01, xanchor="left") if title else None)
    return fig

# clean chart config: no modebar clutter, no logo, keep it presentation-tidy
_PLOT_CFG = {"displayModeBar": False, "displaylogo": False, "responsive": True}

def plot(fig, key):
    st.plotly_chart(fig, use_container_width=True, theme=None, key=key, config=_PLOT_CFG)

@st.cache_data(ttl=1800)
def adzuna_pull_stats():
    """Latest Adzuna pull: postings, categories, MEAN AI exposure (0–1), and the
    change in mean exposure vs the previous pull (a small trend)."""
    root = os.environ.get("LAKE_ROOT", "data").rstrip("/")
    try:
        if root.startswith("s3://"):
            import s3fs
            ep = os.environ.get("S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL_S3")
            fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": ep} if ep else {})
            base = f"{root[len('s3://'):]}/silver/adzuna"
            parts = sorted(fs.glob(f"{base}/dt=*"))
            listcsv = lambda p: fs.glob(f"{p}/*.csv")
            rd = lambda f: (lambda h: pd.read_csv(h))(fs.open(f))
        else:
            import glob
            base = os.path.join(root, "silver", "adzuna")
            parts = sorted(glob.glob(os.path.join(base, "dt=*")))
            listcsv = lambda p: glob.glob(os.path.join(p, "*.csv"))
            rd = lambda f: pd.read_csv(f)
        if not parts:
            return None
        def frame(p):
            fs_ = [rd(f) for f in listcsv(p)]
            return pd.concat(fs_, ignore_index=True) if fs_ else pd.DataFrame()
        cur = frame(parts[-1])
        if cur.empty:
            return None
        exp = round(cur["mean_task_score"].mean(), 2) if "mean_task_score" in cur else None
        delta = None
        if len(parts) > 1 and exp is not None:
            prev = frame(parts[-2])
            if not prev.empty and "mean_task_score" in prev:
                delta = round(exp - prev["mean_task_score"].mean(), 2)
        return {"dt": parts[-1].split("dt=")[-1].strip("/"),
                "n": len(cur), "cats": len(listcsv(parts[-1])),
                "exp": exp, "delta": delta}
    except Exception:
        return None

def render_adzuna_inline():
    """Opened from the badge — the 'Live scheduled ingestion' section, inline."""
    st.markdown("#### Live scheduled ingestion — Adzuna → R2 (daily)")
    df, dt = load_adzuna_latest()
    if df is None or "mean_task_score" not in df or "category" not in df:
        st.info("No live Adzuna data reachable here right now.")
        return
    g = (df.groupby("category").agg(postings=("category", "size"),
                                    exp=("mean_task_score", "mean")).reset_index()
           .sort_values("exp"))
    fig = go.Figure(go.Bar(
        x=g["exp"], y=g["category"], orientation="h", marker_color=AI,
        text=[f"{v:.2f}" for v in g["exp"]], textposition="outside", textfont=dict(color=TXT),
        customdata=g["postings"],
        hovertemplate="<b>%{y}</b><br>mean AI exposure %{x:.2f}<br>%{customdata} postings<extra></extra>"))
    fig.update_xaxes(title="mean AI exposure (0–1)", range=[0, 1])
    plot(base(fig, f"Today's live jobs — mean AI exposure by category  ({dt})", h=300), "adz_inline")
    st.caption("Newest German job postings, pulled daily from the Adzuna API into the R2 lake by Airflow. Full per-category detail is in the 🏗️ Architecture tab.")

def freshness_badge(d):
    """Clickable 'today's live jobs' signal — mean AI exposure + trend; opens a chart."""
    s = adzuna_pull_stats()
    if not s:
        return
    trend = ""
    if s.get("delta") is not None:
        if s["delta"] > 0:   trend = f"  ▲ +{s['delta']:.2f}"
        elif s["delta"] < 0: trend = f"  ▼ {s['delta']:.2f}"
        else:                trend = "  ● flat"
    expbit = f"avg AI exposure {s['exp']:.2f}{trend}" if s.get("exp") is not None else ""
    label = (f"🟢 Today's live jobs  ·  {s['n']} postings  ·  {s['cats']} categories"
             + (f"  ·  {expbit}" if expbit else "") + "     ▸ open live ingestion")
    c1, _ = st.columns([3, 2])
    with c1:
        if st.button(label, key="adzuna_badge", use_container_width=True,
                     help="Newest job postings from the live Adzuna API (→ R2, daily via Airflow). "
                          "Opens the live-ingestion view below."):
            st.session_state["show_adz"] = not st.session_state.get("show_adz", False)
    if st.session_state.get("show_adz"):
        render_adzuna_inline()

def gold_downloads(d):
    """Let a viewer grab the gold tables as CSV."""
    labels = {"adopt_year": "adoption_by_year", "adopt_month": "adoption_by_month",
              "jobs_band": "jobs_by_exposure_band_year", "merge": "github_merge_rate",
              "cr": "github_changes_requested", "churn": "github_churn_by_bucket",
              "ai_repo": "github_ai_share_by_repo"}
    st.caption("Download the gold tables (CSV):")
    cols = st.columns(4)
    i = 0
    for key, fname in labels.items():
        df = d.get(key)
        if df is not None and not df.empty:
            with cols[i % 4]:
                st.download_button(f"⬇ {fname}", df.to_csv(index=False).encode(),
                                   file_name=f"{fname}.csv", mime="text/csv",
                                   key=f"dl_{key}", use_container_width=True)
            i += 1

# The SINGLE data-source boundary. GOLD_BACKEND=postgres reads the warehouse;
# anything else reads the gold CSVs. Swapping backends changes nothing else.
GOLD_BACKEND = os.environ.get("GOLD_BACKEND", "csv")

_GOLD_MAP = {"adopt_year": "github_adoption_by_year",
             "adopt_month": "github_adoption_by_month",
             "jobs_band": "jobs_by_exposure_band_year",
             "merge": "github_merge_rate", "cr": "github_changes_requested",
             "churn": "github_churn_by_bucket", "ai_repo": "github_ai_share_by_repo"}

@st.cache_data(show_spinner="Loading data…")
def load_gold(gold_dir=GOLD):
    if GOLD_BACKEND == "postgres":
        import time
        from sqlalchemy import create_engine
        u=os.environ.get("PGUSER","aiwork"); p=os.environ.get("PGPASSWORD","aiwork")
        h=os.environ.get("PGHOST","localhost"); pt=os.environ.get("PGPORT","5432")
        db=os.environ.get("PGDATABASE","aiwork")
        ssl=os.environ.get("PGSSLMODE","")
        suffix=f"?sslmode={ssl}" if ssl else ""
        eng=create_engine(f"postgresql+psycopg2://{u}:{p}@{h}:{pt}/{db}{suffix}",
                          pool_pre_ping=True,
                          connect_args={"connect_timeout": 10})
        # Neon free tier autosuspends; the first hit after idle may need a few
        # seconds to wake. Retry briefly instead of crashing the first visitor.
        # No blanket except beyond this: a real error still surfaces in the logs.
        last_err = None
        for attempt in range(4):
            try:
                return {key: pd.read_sql(f"select * from gold.{tbl}", eng)
                        for key, tbl in _GOLD_MAP.items()}
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))   # 2s, 4s, 6s — wait for wake-up
        raise last_err
    def rd(name):
        p = os.path.join(gold_dir, name + ".csv")
        return pd.read_csv(p, dtype={"isco08_4digit": str}) if os.path.exists(p) else pd.DataFrame()
    return {k: rd(v) for k, v in _GOLD_MAP.items()}

SILVER_JOBS = os.environ.get("SILVER_JOBS_DIR", "data/silver/kaggle")

@st.cache_data
def load_jobs_silver(base=SILVER_JOBS):
    import glob
    parts = sorted(glob.glob(os.path.join(base, "dt=*")))
    if not parts:
        return pd.DataFrame()
    hits = glob.glob(os.path.join(parts[-1], "*.csv"))
    if not hits:
        return pd.DataFrame()
    df = pd.read_csv(hits[0])
    if "date_published" in df:
        df["date_published"] = pd.to_datetime(df["date_published"], errors="coerce")
    return df

# ---- helper: pool band×year -> one row per band (weighted) ----
def pool_bands(jb, dataset, rate_col):
    b = jb[jb.dataset == dataset].copy()
    if b.empty or rate_col not in b:
        return pd.DataFrame()
    g = (b.groupby(["exposure_order", "exposure_category"])
           .apply(lambda x: pd.Series({
               "postings": x.n_postings.sum(),
               "rate": (x[rate_col] * x.n_postings).sum() / x.n_postings.sum(),
               "avg_exposure": (x.avg_exposure * x.n_postings).sum() / x.n_postings.sum()}))
           .reset_index().sort_values("exposure_order"))
    return g

def chart_adoption(d):
    a = d["adopt_year"].sort_values("year")
    fig = go.Figure(go.Scatter(
        x=a.year.astype(str), y=a.ai_share_pct, mode="lines+markers+text",
        line=dict(color=AI, width=3), marker=dict(size=11, color=AI),
        text=[f"{v:.3f}%" for v in a.ai_share_pct], textposition="top center",
        textfont=dict(color=TXT),
        hovertemplate="<b>%{x}</b><br>AI share: %{y:.4f}%<br>%{customdata[0]:,} of %{customdata[1]:,} commits<extra></extra>",
        customdata=a[["n_ai_commits", "n_commits"]].values))
    fig.update_yaxes(title="AI-signal share of commits (%)")
    return base(fig, "AI adoption in code, by year")

def chart_jobs_usage(d):
    g = pool_bands(d["jobs_band"], "general", "ai_usage_rate")
    fig = go.Figure(go.Bar(
        x=g.rate*100, y=g.exposure_category, orientation="h",
        marker=dict(color=g.avg_exposure, colorscale=[[0, HUMAN], [1, AI]], showscale=False),
        text=[f"{v:.2f}%  (n={int(n):,})" for v, n in zip(g.rate*100, g.postings)],
        textposition="outside", textfont=dict(color=TXT),
        hovertemplate="<b>%{y}</b><br>AI-usage: %{x:.2f}%<br>avg exposure: %{customdata:.2f}<extra></extra>",
        customdata=g.avg_exposure))
    fig.update_xaxes(title="AI-usage demand (%)")
    return base(fig, "General jobs: AI-usage demand by exposure band")

def chart_jobs_building(d):
    g = pool_bands(d["jobs_band"], "tech", "ai_building_rate")
    fig = go.Figure(go.Bar(
        x=g.rate*100, y=g.exposure_category, orientation="h", marker_color=BUILD,
        text=[f"{v:.1f}%  (n={int(n):,})" for v, n in zip(g.rate*100, g.postings)],
        textposition="outside", textfont=dict(color=TXT),
        hovertemplate="<b>%{y}</b><br>AI-building: %{x:.1f}%<extra></extra>"))
    fig.update_xaxes(title="AI-building demand (%)")
    return base(fig, "Tech jobs: AI-building demand by exposure band", h=260)

def chart_jobs_exposure(d):
    g = pool_bands(d["jobs_band"], "general", "ai_usage_rate")
    fig = go.Figure(go.Bar(
        x=g.avg_exposure, y=g.exposure_category, orientation="h",
        marker=dict(color=g.avg_exposure, colorscale=[[0, HUMAN], [1, AI]], showscale=False),
        text=[f"{v:.2f}" for v in g.avg_exposure], textposition="outside", textfont=dict(color=TXT),
        hovertemplate="<b>%{y}</b><br>avg exposure score: %{x:.3f}<extra></extra>"))
    fig.update_xaxes(title="avg AI-exposure score (0–1)")
    return base(fig, "The exposure gradient (clean, monotonic)", h=300)

def chart_usage_trend(d):
    # general AI-usage % by year (weighted across bands) — the 2025->26 rise
    b = d["jobs_band"]; b = b[b.dataset == "general"]
    y = (b.groupby("year").apply(
            lambda x: 100*(x.ai_usage_rate*x.n_postings).sum()/x.n_postings.sum())
         .reset_index(name="usage_pct"))
    y = y[y.year >= 2023]
    fig = go.Figure(go.Scatter(
        x=y.year.astype(str), y=y.usage_pct, mode="lines+markers+text",
        line=dict(color=AI, width=3), marker=dict(size=10),
        text=[f"{v:.2f}%" for v in y.usage_pct], textposition="top center",
        textfont=dict(color=TXT),
        hovertemplate="%{x}: %{y:.2f}% of general postings<extra></extra>"))
    fig.update_yaxes(title="AI-usage demand (%)")
    return base(fig, "AI-usage demand in general jobs is rising", h=300)

def _grouped(df, val, classes, colors, hovunit):
    piv = df.pivot(index="size_bucket", columns="author_class", values=val).reindex(BUCKET_ORDER)
    fig = go.Figure()
    for c, col in zip(classes, colors):
        if c in piv.columns:
            fig.add_bar(name=c, x=BUCKET_ORDER, y=piv[c], marker_color=col,
                        hovertemplate=f"<b>{c}</b><br>%{{x}} lines<br>%{{y:.3f}} {hovunit}<extra></extra>")
    fig.update_layout(barmode="group"); fig.update_xaxes(title="PR / change size (lines)")
    return fig


def _band_trend(jb, dataset, value_col, as_pct=True):
    """One line per exposure band, x=year, y=value_col. Returns plotly fig data."""
    b = jb[jb.dataset == dataset].copy()
    b = b.sort_values(["exposure_order", "year"])
    fig = go.Figure()
    pal = ["#F0A202", "#E86A5C", "#4C9BE8", "#6B7A99", "#9B8Bb4", "#5FA88A"]
    bands = b.sort_values("exposure_order", ascending=False)["exposure_category"].unique()
    for i, band in enumerate(bands):
        s = b[b.exposure_category == band]
        y = s[value_col] * 100 if as_pct else s[value_col]
        fig.add_scatter(x=s.year.astype(str), y=y, name=band, mode="lines+markers",
                        line=dict(color=pal[i % len(pal)], width=2.5), marker=dict(size=7),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:.2f}}"+("%" if as_pct else "")+"<extra></extra>")
    return fig

def chart_demand_trend(d):
    fig = _band_trend(d["jobs_band"], "general", "n_postings", as_pct=False)
    fig.update_yaxes(title="postings")
    return base(fig, "Job demand over time, by exposure level")

def chart_usage_trend_bands(d):
    fig = _band_trend(d["jobs_band"], "general", "ai_usage_rate", as_pct=True)
    fig.update_yaxes(title="AI-usage demand (%)")
    return base(fig, "Demand for AI-usage skills over time, by exposure level")

def chart_building_trend(d):
    fig = _band_trend(d["jobs_band"], "tech", "ai_building_rate", as_pct=True)
    fig.update_yaxes(title="AI-building demand (%)")
    return base(fig, "AI-building (new AI jobs) over time, by exposure level")


def _snapshot_2026(jb, dataset, value_col, title, color="#F0A202"):
    s = jb[(jb.dataset == dataset) & (jb.year == 2026)].sort_values("exposure_order")
    if s.empty:  # tech has no 2026 -> use latest year available
        yr = jb[jb.dataset == dataset].year.max()
        s = jb[(jb.dataset == dataset) & (jb.year == yr)].sort_values("exposure_order")
        title = title + f" ({int(yr)})"
    else:
        title = title + " (2026)"
    hits = (s[value_col] * s.n_postings).round().astype(int)
    fig = go.Figure(go.Bar(
        x=s[value_col]*100, y=s.exposure_category, orientation="h", marker_color=color,
        text=[f"{v*100:.1f}%  (n={n:,}, {h} hits)" for v, n, h in zip(s[value_col], s.n_postings, hits)],
        textposition="outside", textfont=dict(color="#E6E8EC"),
        hovertemplate="<b>%{y}</b><br>%{x:.2f}%<extra></extra>"))
    fig.update_xaxes(title="%")
    return base(fig, title, h=300)

def chart_usage_snap(d):
    return _snapshot_2026(d["jobs_band"], "general", "ai_usage_rate",
                          "AI-usage demand by exposure level", "#F0A202")

def chart_building_snap(d):
    return _snapshot_2026(d["jobs_band"], "tech", "ai_building_rate",
                          "AI-building by exposure level", "#4C9BE8")



def chart_demand_month_all(sv):
    """Full-span (2022-2026) monthly job demand, line per exposure level, from silver."""
    if sv.empty or "date_published" not in sv:
        return None
    s = sv.dropna(subset=["date_published"]).copy()
    if s.empty:
        return None
    s["month"] = s.date_published.dt.to_period("M").astype(str)
    g = (s.groupby(["exposure_order","exposure_category","month"])
           .size().reset_index(name="postings").sort_values(["exposure_order","month"]))
    pal = ["#F0A202","#E86A5C","#4C9BE8","#6B7A99","#9B8Bb4","#5FA88A"]
    fig = go.Figure()
    for i, band in enumerate(g.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        b = g[g.exposure_category == band]
        fig.add_scatter(x=b.month, y=b.postings, name=band, mode="lines",
                        line=dict(color=pal[i%len(pal)], width=2),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:,}} postings<extra></extra>")
    fig.update_yaxes(title="postings")
    fig.update_xaxes(title="month")
    return base(fig, "Job demand over time (monthly) by exposure level")

def chart_demand_share(d):
    """Job demand over time = postings per exposure level per year (line per band)."""
    b = d["jobs_band"]; b = b[b.dataset == "general"].sort_values(["exposure_order","year"])
    pal = ["#F0A202","#E86A5C","#4C9BE8","#6B7A99","#9B8Bb4","#5FA88A"]
    fig = go.Figure()
    for i, band in enumerate(b.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        s = b[b.exposure_category == band]
        fig.add_scatter(x=s.year.astype(str), y=s.n_postings, name=band, mode="lines+markers",
                        line=dict(color=pal[i%len(pal)], width=2.5), marker=dict(size=7),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:,}} postings<extra></extra>")
    fig.update_yaxes(title="postings")
    return base(fig, "Job demand over time by exposure level")

def chart_usage_year(d):
    b = d["jobs_band"]; b = b[b.dataset == "general"].sort_values(["exposure_order","year"])
    pal = ["#F0A202","#E86A5C","#4C9BE8","#6B7A99","#9B8Bb4","#5FA88A"]
    fig = go.Figure()
    for i, band in enumerate(b.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        s = b[b.exposure_category == band]
        fig.add_scatter(x=s.year.astype(str), y=s.ai_usage_rate*100, name=band, mode="lines+markers",
                        line=dict(color=pal[i%len(pal)], width=2.5), marker=dict(size=7),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:.2f}}%<extra></extra>")
    fig.update_yaxes(title="AI-usage demand (%)")
    return base(fig, "Demand for AI-usage skills by year")

def chart_usage_month_2026(sv):
    """2026 monthly AI-usage ramp, from silver."""
    if sv.empty or "date_published" not in sv:
        return None
    s = sv[sv.date_published.dt.year == 2026].copy()
    if s.empty:
        return None
    s["month"] = s.date_published.dt.to_period("M").astype(str)
    g = s.groupby("month").agg(postings=("has_ai_usage","size"),
                               usage=("has_ai_usage","sum")).reset_index()
    g["pct"] = 100*g.usage/g.postings
    fig = go.Figure(go.Scatter(
        x=g.month, y=g.usage, mode="lines+markers+text", line=dict(color="#F0A202", width=3),
        marker=dict(size=9), text=g.usage, textposition="top center", textfont=dict(color="#E6E8EC"),
        hovertemplate="%{x}<br>%{y} usage postings of %{customdata}<extra></extra>",
        customdata=g.postings))
    fig.update_yaxes(title="AI-usage postings (count)")
    return base(fig, "AI-usage demand ramping through 2026 (monthly)", h=320)


@st.cache_data
def load_tech_silver(base=None):
    import glob
    base = base or os.environ.get("SILVER_TECH_DIR", "data/silver/tech")
    parts = sorted(glob.glob(os.path.join(base, "dt=*")))
    if not parts: return pd.DataFrame()
    hits = glob.glob(os.path.join(parts[-1], "*.csv"))
    if not hits: return pd.DataFrame()
    df = pd.read_csv(hits[0])
    if "posted_date" in df:
        df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    return df

def chart_tech_demand_month(sv):
    """Full-span monthly tech job demand, line per exposure level, from tech silver."""
    if sv.empty or "posted_date" not in sv:
        return None
    s = sv.dropna(subset=["posted_date"]).copy()
    if s.empty: return None
    s["month"] = s.posted_date.dt.to_period("M").astype(str)
    g = (s.groupby(["exposure_order","exposure_category","month"])
           .size().reset_index(name="postings").sort_values(["exposure_order","month"]))
    pal = ["#4C9BE8","#F0A202","#E86A5C","#6B7A99","#9B8Bb4","#5FA88A"]
    fig = go.Figure()
    for i, band in enumerate(g.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        b = g[g.exposure_category == band]
        fig.add_scatter(x=b.month, y=b.postings, name=band, mode="lines",
                        line=dict(color=pal[i%len(pal)], width=2),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:,}} postings<extra></extra>")
    fig.update_yaxes(title="postings"); fig.update_xaxes(title="month")
    return base(fig, "Tech job demand over time (monthly) by exposure level")

def chart_tech_demand(d):
    """Tech job demand over time, line per exposure level (same style as general)."""
    b = d["jobs_band"]; b = b[b.dataset == "tech"].sort_values(["exposure_order","year"])
    pal = ["#4C9BE8","#F0A202","#E86A5C","#6B7A99","#9B8Bb4","#5FA88A"]
    fig = go.Figure()
    for i, band in enumerate(b.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        s = b[b.exposure_category == band]
        fig.add_scatter(x=s.year.astype(str), y=s.n_postings, name=band, mode="lines+markers",
                        line=dict(color=pal[i%len(pal)], width=2.5), marker=dict(size=8),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:,}} postings<extra></extra>")
    fig.update_yaxes(title="postings")
    return base(fig, "Tech job demand over time by exposure level")

def chart_tech_building_year(d):
    b = d["jobs_band"]; b = b[b.dataset == "tech"].sort_values(["exposure_order","year"])
    pal = ["#4C9BE8","#F0A202","#E86A5C","#6B7A99"]
    fig = go.Figure()
    for i, band in enumerate(b.sort_values("exposure_order", ascending=False).exposure_category.unique()):
        s = b[b.exposure_category == band]
        fig.add_scatter(x=s.year.astype(str), y=s.ai_building_rate*100, name=band, mode="lines+markers",
                        line=dict(color=pal[i%len(pal)], width=2.5), marker=dict(size=8),
                        hovertemplate=f"{band}<br>%{{x}}: %{{y:.1f}}%<extra></extra>")
    fig.update_yaxes(title="AI-building demand (%)")
    return base(fig, "AI-building demand by year (tech)")

def chart_merge(d):
    fig = _grouped(d["merge"], "merged_rate", ["ai_agent", "baseline"], [AI, HUMAN], "")
    fig.update_yaxes(title="merge rate", range=[0, 1])
    return base(fig, "PR acceptance: agent vs human, by size")

def chart_churn(d):
    fig = _grouped(d["churn"], "mean_followup", ["ai_agent", "ai_coauthor", "human"], [AI, ASSIST, HUMAN], "lines")
    fig.update_yaxes(title="mean 14-day follow-up churn (lines)")
    return base(fig, "Code durability: follow-up churn by class, by size")

def chart_repo(d):
    r = d["ai_repo"].sort_values("ai_pct")
    fig = go.Figure(go.Bar(
        x=r.ai_pct, y=r.repo, orientation="h", marker_color=AI,
        text=[f"{v:.1f}%" for v in r.ai_pct], textposition="outside", textfont=dict(color=TXT),
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% AI touches<extra></extra>"))
    fig.update_xaxes(title="AI share of file-touches (%)")
    return base(fig, "AI adoption varies by repo", h=260)


# ---------------------------------------------------------------------------
# ILO-style exposure landscape: one dot per occupation, x=mean score,
# y=task-variability (sd), coloured by exposure gradient.  Data = ILO reference.
# ---------------------------------------------------------------------------
ILO_REF = os.environ.get("ILO_FILE", "reference/ilo_ai_exposure_isco08.csv")
ISCO_MAJOR = {"1": "Managers", "2": "Professionals", "3": "Technicians",
              "4": "Clerical support", "5": "Services & sales",
              "6": "Agriculture, forestry & fishery", "7": "Craft & trades",
              "8": "Plant & machine operators", "9": "Elementary occupations",
              "0": "Armed forces"}

@st.cache_data
def load_ilo_reference(path=ILO_REF):
    try:
        return pd.read_csv(path, dtype={"isco08_4digit": str})
    except Exception:
        return pd.DataFrame()

def _grad(cat):
    c = str(cat).lower()
    if "gradient 4" in c or "highest" in c:      return ("#8E1B16", 4, "Highest exposure (gradient 4)")
    if "gradient 3" in c or "significant" in c:  return ("#E24A5C", 3, "Significant exposure (gradient 3)")
    if "gradient 2" in c or "moderate" in c:     return ("#F0A202", 2, "Moderate exposure (gradient 2)")
    if "gradient 1" in c or "low exposure" in c: return ("#F2D45C", 1, "Low exposure (gradient 1)")
    if "minimal" in c:                           return ("#4EC5C1", 0, "Minimal exposure")
    if "not exposed" in c or "no exposure" in c: return ("#8B93A7", -1, "Not exposed")
    return ("#6B7A99", -2, str(cat))

def chart_exposure_snapshot(sv, year):
    """ILO-style snapshot: occupations POSTED in `year`, positioned by exposure
    (x=mean score, y=task sd), coloured by gradient, sized by # postings."""
    need = {"mean_task_score", "sd_task_score", "exposure_category"}
    if sv.empty or not need.issubset(sv.columns) or "date_published" not in sv:
        return None
    s = sv.copy()
    s["year"] = s["date_published"].dt.year
    s = s[s["year"] == year].dropna(subset=["mean_task_score", "sd_task_score"])
    if s.empty:
        return None
    key = "isco08_4digit" if "isco08_4digit" in s else "occupation_name"
    name = "occupation_name" if "occupation_name" in s else key
    g = (s.groupby(key)
           .agg(occ=(name, "first"),
                x=("mean_task_score", "mean"),
                y=("sd_task_score", "mean"),
                cat=("exposure_category", "first"),
                n=(name, "size"))
           .reset_index())
    fig = go.Figure()
    cats = sorted(g["cat"].dropna().unique(), key=lambda c: -_grad(c)[1])
    sref = 2.0 * g["n"].max() / (34 ** 2)
    for cat in cats:
        d = g[g["cat"] == cat]
        color, _r, label = _grad(cat)
        fig.add_scatter(
            x=d["x"], y=d["y"], mode="markers", name=label,
            marker=dict(size=d["n"], sizemode="area", sizeref=sref, sizemin=5,
                        color=color, line=dict(width=1, color=BG), opacity=0.9),
            customdata=list(zip(d["occ"], d["n"])),
            hovertemplate="<b>%{customdata[0]}</b><br>avg score %{x:.2f} · task sd %{y:.2f}"
                          "<br>%{customdata[1]:,} postings<extra></extra>")
    fig.update_xaxes(title="Average exposure score", range=[0, 0.8])
    fig.update_yaxes(title="Standard deviation (task variability)", range=[0, 0.26])
    fig.update_layout(legend=dict(orientation="v", x=1.01, y=1, xanchor="left"))
    return base(fig, f"AI-exposure of occupations posted in {year}  ·  bubble = # postings", h=560)

# ---------------------------------------------------------------------------
# Live scheduled ingestion — read the latest Adzuna partition from the lake
# (R2 / S3 / local). Degrades gracefully so the deployed app never breaks.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800)
def load_adzuna_latest():
    root = os.environ.get("LAKE_ROOT", "data").rstrip("/")
    try:
        if root.startswith("s3://"):
            import s3fs
            ep = os.environ.get("S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL_S3")
            fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": ep} if ep else {})
            base = f"{root[len('s3://'):]}/silver/adzuna"
            parts = sorted(fs.glob(f"{base}/dt=*"))
            if not parts:
                return None, None
            latest = parts[-1]
            dt = latest.split("dt=")[-1].strip("/")
            frames = []
            for f in fs.glob(f"{latest}/*.csv"):
                with fs.open(f) as fh:
                    df = pd.read_csv(fh)
                df["category"] = f.split("/")[-1].replace("de_", "").replace(".csv", "")
                frames.append(df)
        else:
            import glob
            base = os.path.join(root, "silver", "adzuna")
            parts = sorted(glob.glob(os.path.join(base, "dt=*")))
            if not parts:
                return None, None
            latest = parts[-1]
            dt = os.path.basename(latest).replace("dt=", "")
            frames = []
            for f in glob.glob(os.path.join(latest, "*.csv")):
                df = pd.read_csv(f)
                df["category"] = os.path.basename(f).replace("de_", "").replace(".csv", "")
                frames.append(df)
        if not frames:
            return None, None
        return pd.concat(frames, ignore_index=True), dt
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Architecture / lineage renderers for the new tab
# ---------------------------------------------------------------------------
_ARCH_SVG = """
<svg viewBox="0 0 1160 410" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">
  <defs>
    <marker id="arr" markerWidth="10" markerHeight="10" refX="7" refY="4" orient="auto">
      <path d="M0,0 L8,4 L0,8 Z" fill="#E6EAF3"/>
    </marker>
    <marker id="arrO" markerWidth="10" markerHeight="10" refX="7" refY="4" orient="auto">
      <path d="M0,0 L8,4 L0,8 Z" fill="#F0A202"/>
    </marker>
    <style>
      .box{fill:none;stroke:#4A5470;stroke-width:1.6}
      .acc{fill:none;stroke:#F0A202;stroke-width:2}
      .lbl{fill:#FFFFFF;font:600 18px Inter,system-ui,sans-serif}
      .li{fill:#E6EAF3;font:400 15px Inter,system-ui,sans-serif}
      .sub{fill:#C6CDDD;font:400 14px Inter,system-ui,sans-serif}
      .cap{fill:#AAB2C4;font:italic 400 13px Inter,system-ui,sans-serif}
      .flow{stroke:#E6EAF3;stroke-width:2.6;fill:none;marker-end:url(#arr)}
      .orc{stroke:#F0A202;stroke-width:2.2;stroke-dasharray:5 4;fill:none;marker-end:url(#arrO)}
      .otag{fill:#FBBF3A;font:600 13px Inter,system-ui,sans-serif}
    </style>
  </defs>

  <rect x="0" y="0" width="1160" height="410" fill="#0E1117"/>

  <!-- Airflow -->
  <rect class="acc" x="300" y="20" width="560" height="58" rx="12"/>
  <text class="lbl" x="580" y="45" text-anchor="middle">Airflow — orchestration + scheduling</text>
  <text class="sub" x="580" y="66" text-anchor="middle">triggers the daily Adzuna pull · runs the on-demand load → dbt rebuild</text>

  <!-- Batch sources (host-ingested, NOT scheduled) -->
  <rect class="box" x="24" y="110" width="236" height="168" rx="12"/>
  <text class="lbl" x="142" y="136" text-anchor="middle">Batch sources</text>
  <text class="li"  x="44" y="162">• Jobs — all domains</text>
  <text class="li"  x="44" y="184">• Tech jobs</text>
  <text class="li"  x="44" y="206">• GH Archive (code events)</text>
  <text class="li"  x="44" y="228">• Git repos (churn)</text>
  <text class="cap" x="142" y="258" text-anchor="middle">host ingestion + ML enrichment</text>

  <!-- Scheduled source -->
  <rect class="acc" x="24" y="300" width="236" height="78" rx="12"/>
  <text class="lbl" x="142" y="330" text-anchor="middle">Adzuna API</text>
  <text class="otag" x="142" y="352" text-anchor="middle">@daily scheduled pull</text>

  <!-- Lake -->
  <rect class="box" x="330" y="150" width="196" height="120" rx="12"/>
  <text class="lbl" x="428" y="182" text-anchor="middle">Lake · Cloudflare R2</text>
  <text class="li"  x="428" y="210" text-anchor="middle">bronze/  (raw)</text>
  <text class="li"  x="428" y="234" text-anchor="middle">silver/  (cleaned)</text>

  <!-- Warehouse -->
  <rect class="box" x="596" y="150" width="220" height="120" rx="12"/>
  <text class="lbl" x="706" y="182" text-anchor="middle">Warehouse · Neon</text>
  <text class="li"  x="706" y="210" text-anchor="middle">silver.*  →  gold.*</text>
  <text class="li"  x="706" y="234" text-anchor="middle">gold built by dbt</text>

  <!-- Streamlit -->
  <rect class="box" x="886" y="150" width="196" height="120" rx="12"/>
  <text class="lbl" x="984" y="182" text-anchor="middle">Streamlit</text>
  <text class="li"  x="984" y="210" text-anchor="middle">public dashboard</text>
  <text class="sub" x="984" y="234" text-anchor="middle">(this app)</text>

  <!-- data-flow arrows -->
  <path class="flow" d="M260,200 L328,205"/>
  <path class="flow" d="M260,332 C300,332 320,285 344,272"/>
  <path class="flow" d="M526,210 L594,210"/>
  <path class="flow" d="M816,210 L884,210"/>

  <!-- Airflow orchestration arrows -->
  <path class="orc" d="M320,78 C230,120 150,220 142,298"/>
  <text class="otag" x="196" y="150" text-anchor="middle" transform="rotate(-2 196 150)">triggers daily</text>
  <path class="orc" d="M660,78 L700,148"/>
  <text class="otag" x="712" y="118" text-anchor="start">load + dbt</text>

  <!-- legend -->
  <line x1="330" y1="360" x2="360" y2="360" stroke="#AEB6C8" stroke-width="2.2" marker-end="url(#arr)"/>
  <text class="sub" x="368" y="364">data flow</text>
  <line x1="470" y1="360" x2="500" y2="360" stroke="#F0A202" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arrO)"/>
  <text class="sub" x="508" y="364">Airflow orchestration / trigger</text>
  <text class="cap" x="1082" y="364" text-anchor="end">provider-agnostic lake (S3 / R2 / MinIO) · ~$0/mo on free tiers</text>
</svg>
"""

def render_architecture():
    st.markdown("### Cloud architecture")
    st.markdown(f"<p style='color:{MUTED};margin-top:-6px'>Raw sources → object-storage lake (R2) → managed Postgres warehouse (Neon, gold built by dbt) → this dashboard. Airflow orchestrates and runs the daily Adzuna ingestion.</p>", unsafe_allow_html=True)
    components.html(
        f"<style>html,body{{margin:0;padding:0;background:{BG}}}</style>{_ARCH_SVG}",
        height=440, scrolling=False)

    st.markdown("#### The stack")
    st.markdown(
        "| Layer | Tool / what happens |\n|---|---|\n"
        "| Data lake | **Cloudflare R2** — S3-compatible object storage (bronze + silver) |\n"
        "| Warehouse | **Neon** — managed Postgres (silver + gold) |\n"
        "| Silver transformation (Python) | **ESCO embedding crosswalk** (job title → ISCO-08, semantic match) · **AI-skill tagger** (regex/anchors) · **ISCO→ILO exposure join** · GH-Archive parsing · **PyDriller** churn mining |\n"
        "| Gold transformation (dbt) | **SQL models** aggregate silver → the 8 gold tables, + data tests |\n"
        "| Orchestration / schedule | **Airflow** (Docker) — daily Adzuna ingestion + on-demand rebuild |\n"
        "| Serving | **Streamlit Community Cloud** + Plotly |\n"
        "| Portability | **Point the lake at Cloudflare R2** (or AWS S3 / MinIO) with one endpoint setting — same code, no rewrite |")
    note("Transformation lives in two places by design: the <b>heavy, procedural</b> work (embeddings, tagging, git mining) is Python; the <b>set-based aggregation</b> (silver→gold) is dbt SQL.")

def render_lineage():
    st.markdown("#### Data lineage by pillar")
    note("Source shown as <b>file / dataset</b> — <i>what it is</i>. Silver and gold cells name the table/columns plus <i>what they hold</i>.")
    with st.expander("🧑\u200d💻  Pillar 1 — AI in code (GitHub)", expanded=True):
        st.markdown(
            "| Signal | Source in lake — *what it is* | Silver — *what it holds* | Gold — *what it holds* |\n|---|---|---|---|\n"
            "| **Adoption** (AI commit share) | **`bronze/gharchive/`** — *22 monthly hourly GH Archive samples; every public commit & PR event* | `gh_matches` *(commits carrying an AI-authorship signal)* · `gh_totals` *(all-commit counts = the denominator)* | `github_adoption_by_year` / `_by_month` *(AI-signal share of commits over time)* |\n"
            "| **Merge rate** (acceptance) | **`bronze/gharchive_fullday/`** — *4 full sampled days (24 h each); closed-PR events* | `gh_pr_outcomes` *(one row per closed PR: merged?, size, hours-open, author class)* | `github_merge_rate` *(merge rate by author-class × size band)* |\n"
            "| **Changes requested** (review) | **`bronze/gharchive_fullday/`** — *same full days; pull-request review events* | `gh_pr_reviews` *(one row per review + its state)* | `github_changes_requested` *(rate of change-request reviews)* |\n"
            "| **Durability** (churn) | **git repos** (airbyte · cal.com · OpenHands) — *full commit history mined with PyDriller* | `gh_churn_events` *(one row per file-touch + 14-day follow-up churn, by author class)* | `github_churn_by_bucket` *(mean follow-up churn by class × size)* · `github_ai_share_by_repo` *(AI share of touches per repo)* |")
        note(
            "<b>Why these three repos?</b> Chosen to span a range of AI adoption while all being large, active, public projects "
            "with rich PR + commit history (what PyDriller needs): <b>OpenHands ~59%</b>, <b>cal.com ~53%</b>, <b>airbyte ~27%</b> of "
            "file-touches are AI-attributed. OpenHands is itself an AI-agent project (high AI authorship); airbyte and cal.com "
            "are mainstream, largely human-led OSS — giving a high-vs-low contrast rather than a random pick.")
    with st.expander("💼  Pillar 2 — AI in the job market", expanded=True):
        st.markdown(
            "| Signal | Source in lake — *what it is* | Silver — *what it holds* | Gold — *what it holds* |\n|---|---|---|---|\n"
            "| **Occupation** (ISCO-08) | **`silver/kaggle` + `silver/tech`** job titles + **ESCO taxonomy** — *free-text titles matched to a standard occupation code* | `isco08_4digit` *(mapped code)* · `match_method` / `match_score` *(how it matched + confidence)* | `jobs_by_occupation` *(postings + AI rates per occupation)* |\n"
            "| **AI-exposure** | ISCO code + **ILO AI-exposure file** — *per-occupation GenAI exposure score* | `exposure_category` *(gradient band)* · `exposure_order` *(band rank)* · `mean_task_score` *(0–1 exposure)* · `exposure_imputed` *(filled from parent code?)* | `jobs_by_exposure_band_year` (`avg_exposure`) *(mean exposure per band × year)* |\n"
            "| **AI-usage demand** | job **title + description** — *employers wanting AI-literate workers: people expected to use AI tools in the role* (AI-skill tagger) | `has_ai_usage` *(posting asks for AI-use skills)* | `jobs_by_exposure_band_year` (`ai_usage_rate`) *(share of postings wanting AI-users)* |\n"
            "| **AI-building demand** | job **skills + description** — *roles that build AI/ML systems* (AI-skill tagger) | `has_ai_building` *(posting is an AI/ML-building role)* | `jobs_by_exposure_band_year` (`ai_building_rate`) *(share of AI-building roles)* |")

    with st.expander("📚  Reference standards (ISCO-08 · ESCO · ILO exposure) — what they are & where they come from"):
        st.markdown("<div style='font-size:15.5px;line-height:1.65;color:#D3D9E6'>", unsafe_allow_html=True)
        st.markdown(
            "**ISCO-08** — the *International Standard Classification of Occupations* (2008), maintained by the **ILO**. "
            "A global system of **436 four-digit occupation codes**; the common language every job title is mapped to.\n\n"
            "**ESCO** — *European Skills, Competences, Qualifications and Occupations*, the EU's multilingual "
            "occupation/skill taxonomy (**European Commission**). Every ESCO occupation carries its ISCO-08 code, so "
            "matching a free-text title to the nearest ESCO label yields a standard ISCO code. (We match by meaning using "
            "sentence-embeddings, not keywords.)\n\n"
            "**ILO AI-exposure scores** — from the ILO study *Generative AI and Jobs* (Gmyrek et al.). For each ISCO-08 "
            "occupation, its **typical tasks** (from the official ISCO-08 documentation) are scored by an LLM (GPT-4), "
            "validated against expert surveys, for how exposed they are to generative AI. Task scores aggregate to an "
            "occupation-level **mean score (0–1)**, then binned into **four progressively increasing exposure gradients** "
            "based on the mean score and task variability. Higher = more of the occupation's tasks are exposed to GenAI. "
            "\n\n🔗 [ILO — Generative AI and Jobs (2025 refined index)](https://www.ilo.org/publications/generative-ai-and-jobs-2025-update)")
        st.markdown("</div>", unsafe_allow_html=True)

def render_adzuna_live():
    st.markdown("#### Live scheduled ingestion — Adzuna → R2 (daily)")
    df, dt = load_adzuna_latest()
    if df is None:
        st.info("Latest Adzuna partition isn't reachable from here (needs `LAKE_ROOT` + R2 credentials in the environment). Locally, or with R2 secrets set, this panel shows the most recent daily pull.")
        return
    cats = int(df["category"].nunique()) if "category" in df else 0
    mapped_pct = 100 * (df["isco08_4digit"].astype(str) != "unmapped").mean() if "isco08_4digit" in df else 0
    c1, c2, c3 = st.columns(3)
    kpi(c1, "Last pull", str(dt), "most recent dt= partition")
    kpi(c2, "Job categories", str(cats), "pulled this run")
    kpi(c3, "Postings", f"{len(df):,}", f"{mapped_pct:.0f}% mapped to an ISCO code")

    note("<b>Job categories and their AI-exposure</b> (from the enriched silver) — postings, mean AI-exposure (0–1), and AI-skill demand per category:")
    if "category" in df:
        g = df.groupby("category").agg(postings=("category", "size"))
        if "mean_task_score" in df:
            g["mean_ai_exposure"] = df.groupby("category")["mean_task_score"].mean().round(2)
        if "has_ai_skill" in df:
            g["ai_skill_%"] = (100 * df.groupby("category")["has_ai_skill"].mean()).round(0)
        if "has_salary" in df:
            g["with_salary_%"] = (100 * df.groupby("category")["has_salary"].mean()).round(0)
        g = g.reset_index().sort_values("mean_ai_exposure", ascending=False) if "mean_ai_exposure" in g else g.reset_index()
        st.dataframe(g, hide_index=True, use_container_width=True)

    note(
        "Each Adzuna silver row is a live job posting enriched to the same shape as the batch data — occupation code, "
        "ILO exposure band + score, and AI-usage/-building flags. It lands daily in R2 via the <b>aiwork_adzuna_daily</b> "
        "Airflow DAG (the pipeline's live data-collection engine). Descriptions are short here, so AI-skill % reads low — "
        "the deep AI-usage/-building analysis above uses the full-text batch datasets.")


def kpi(col, label, value, sub):
    col.markdown(
        f"<div style='background:{PANEL};border:1px solid {GRID};border-radius:14px;padding:16px 18px'>"
        f"<div style='color:{MUTED};font-size:12px;text-transform:uppercase;letter-spacing:.06em'>{label}</div>"
        f"<div style='color:{TXT};font-size:28px;font-weight:700;margin:4px 0'>{value}</div>"
        f"<div style='color:{MUTED};font-size:12px'>{sub}</div></div>", unsafe_allow_html=True)

def explain(what, why, caveat):
    st.markdown(f"**What you're seeing** \u00b7 {what}")
    st.markdown(f"**Why it matters** \u00b7 {why}")
    st.info(f"**Honest limitation** \u00b7 {caveat}")

def note(text):
    st.markdown(f"<p style='font-size:15.5px;line-height:1.6;color:#D3D9E6;margin:6px 0 10px'>{text}</p>", unsafe_allow_html=True)

def infobox(text, col=None):
    """Small 'what this means' panel; pass a column to place it under a card."""
    html = (f"<div style='font-size:12.5px;line-height:1.5;color:#C7CEDE;background:{PANEL};"
            f"border:1px solid {GRID};border-radius:8px;padding:8px 11px;margin:6px 0 2px'>{text}</div>")
    (col.markdown if col is not None else st.markdown)(html, unsafe_allow_html=True)

def small_n_note(df, klass_col, n_col, klass="ai_agent", threshold=1000, unit="PRs"):
    """Visible small-sample warning when a class's counts are thin vs the rest."""
    if df is None or df.empty or klass_col not in df or n_col not in df:
        return
    s = df[df[klass_col] == klass]
    other = df[df[klass_col] != klass]
    if s.empty:
        return
    hi = int(s[n_col].max())
    if hi < threshold:
        lo = int(s[n_col].min())
        rng = f"{lo:,}" if lo == hi else f"{lo:,}–{hi:,}"
        base = f" vs {int(other[n_col].max()):,} for the baseline" if not other.empty else ""
        st.warning(f"⚠ Small sample — autonomous-agent {unit}: **{rng}**{base}. "
                   f"Read the agent bars as **directional**, not precise rates.")

def main():
    st.set_page_config(page_title="AI \u00d7 Work", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(f"""<style>.stApp{{background:{BG};}}.block-container{{padding-top:2rem;max-width:1200px;}}h1,h2,h3,h4{{color:{TXT};}}[data-testid=\"stMarkdownContainer\"] p,[data-testid=\"stMarkdownContainer\"] li,[data-testid=\"stMarkdownContainer\"] td,[data-testid=\"stMarkdownContainer\"] th{{color:{TXT};}}</style>""", unsafe_allow_html=True)
    d = load_gold()
    st.title("AI \u00d7 Work")
    st.markdown(f"<p style='color:{MUTED};font-size:16px;margin-top:-8px'>How AI is reshaping code and the German job market \u2014 a bronze\u2192silver\u2192gold pipeline on R2 + Neon + dbt, served live. Hover any chart for detail; see the \U0001F3D7\uFE0F Architecture tab for how it's built.</p>", unsafe_allow_html=True)
    freshness_badge(d)

    c1, c2, c3, c4 = st.columns(4)
    ay = d["adopt_year"].sort_values("year")
    if len(ay):
        kpi(c1, "AI in code, 2025", f"{ay.ai_share_pct.iloc[-1]:.2f}%", f"up from {ay.ai_share_pct.iloc[0]:.3f}% in {int(ay.year.iloc[0])}")
    tb = pool_bands(d["jobs_band"], "tech", "ai_building_rate")
    if len(tb):
        kpi(c2, "Tech jobs building AI", f"{100*(tb.rate*tb.postings).sum()/tb.postings.sum():.0f}%", "vs ~0% in the general market")
    if len(d["merge"]):
        mm = d["merge"].groupby("author_class").apply(lambda g:(g.merged_rate*g.n_prs).sum()/g.n_prs.sum())
        if {"ai_agent","baseline"}.issubset(mm.index):
            kpi(c3, "Agent PR merge gap", f"{(mm['baseline']-mm['ai_agent'])*100:.0f} pts", "accepted less, size-controlled")
    if len(d["ai_repo"]):
        kpi(c4, "AI share by repo", f"{d['ai_repo'].ai_pct.min():.0f}\u2013{d['ai_repo'].ai_pct.max():.0f}%", "varies widely across projects")

    st.write("")
    tS, t1, t2, t3, t4, t5, t6, tM = st.tabs(["\U0001F3AF Summary", "\U0001F4C8 Adoption", "\U0001F4BC Jobs", "\u2705 Acceptance", "\U0001F527 Durability", "\U0001F517 Synthesis", "\U0001F3D7\uFE0F Architecture", "\U0001F4CB Methods"])

    with tS:
        st.markdown("### The story in 30 seconds")
        note("Two questions, one shift: <b>is AI entering real code</b>, and <b>is the job market reacting</b>? Short answer — a sharp yes to the first in 2025, and the labour market is starting to follow, concentrated where work is most AI-exposed.")

        st.markdown("#### 🧑\u200d💻 AI in code")
        a, b, c = st.columns(3)
        if len(ay):
            kpi(a, "AI-signal commits, 2025", f"{ay.ai_share_pct.iloc[-1]:.2f}%",
                f"from {ay.ai_share_pct.iloc[0]:.3f}% in {int(ay.year.iloc[0])} — ~20×")
            infobox("Share of all public commits in 2025 carrying an AI-authorship signal — the clearest sign AI is entering real codebases.", a)
        if len(d["merge"]) and {"ai_agent", "baseline"}.issubset(mm.index):
            gap = (mm["baseline"] - mm["ai_agent"]) * 100
            kpi(b, "Agent PR merge gap", f"{gap:.0f} pp", "percentage points, size-controlled")
            infobox(f"‘pp’ = percentage points. Human/baseline PRs merge ~{mm['baseline']*100:.0f}%, autonomous-agent PRs ~{mm['ai_agent']*100:.0f}% at the same size — a {gap:.0f}-point acceptance gap, not proven worse code.", b)
        kpi(c, "Code durability", "AI ≤ human", "reworked no more, at equal size")
        infobox("At equal change size, AI-touched files are rewritten within 14 days no more than human-touched ones — contradicts the ‘AI is sloppier’ prior.", c)
        note("<b>Takeaway:</b> attributable AI authorship in real repos jumped ~20× into 2025; agent PRs are accepted a little less (looks like process/trust, not obviously worse code), and AI-touched code is reworked no more than human code.")

        st.divider()
        st.markdown("#### 💼 AI in the job market")
        e, f_, g_ = st.columns(3)
        if len(tb):
            kpi(e, "Tech roles building AI", f"{100*(tb.rate*tb.postings).sum()/tb.postings.sum():.0f}%",
                "vs ~0% in the general market")
            infobox("Of tech-sector postings, the share that are AI/ML-<b>building</b> roles (ML engineer, data scientist, MLOps). ~0% in the all-domains market — building AI is a tech story.", e)
        # AI-usage in the general market — a robust count (rates go to 0 in thin bands)
        _gj = d["jobs_band"]; _gj = _gj[_gj.dataset == "general"] if len(_gj) else _gj
        _cnt = None
        if len(_gj) and "ai_usage_rate" in _gj and "n_postings" in _gj:
            _cnt = int(round((_gj.ai_usage_rate * _gj.n_postings).sum()))
        if _cnt:
            kpi(f_, "AI-usage postings", f"{_cnt:,}", "general ads wanting AI-users")
            infobox("How many general job ads ask for workers who can <b>use</b> AI tools (not build them). Emerging in 2026 and concentrated in AI-exposed roles — small in absolute terms, but new.", f_)
        else:
            kpi(f_, "AI-usage demand", "2026", "emerging, in AI-exposed roles")
            infobox("Demand for workers who can <b>use</b> AI tools (not build them). Near-zero before, emerges in 2026, concentrated in AI-exposed occupations.", f_)
        kpi(g_, "Exposure gradient", "clean", "monotonic across bands")
        infobox("Order occupations by ILO exposure band (1→4) and average exposure rises steadily across bands, no reversals — a coherence check that the exposure scale behaves as expected.", g_)
        note("<b>Takeaway:</b> <i>building</i> AI is a tech-sector story (~40–57% of tech roles); wanting workers who <i>use</i> AI is newer (2026) and concentrates in AI-exposed occupations.")

        st.divider()
        note("<b>Bottom line:</b> AI is entering code fast, and the labour market is beginning to reprice AI skills — visible first where task exposure is highest. Open each tab for the detail, 🏗️ Architecture for how it's built, and 📋 Methods for the honest caveats.")

    with t1:
        plot(chart_adoption(d), "chart_1")
        explain("The share of commits carrying an AI-authorship signal, each year.",
                "Clearest evidence AI is entering real codebases \u2014 with a sharp 2025 takeoff.",
                "Counts only *attributable* AI (co-author trailers + known agents); silent Copilot leaves no git trace, so this is a floor.")

    with t2:
        st.markdown("### AI-exposure landscape — yearly snapshot")
        note("A single-year snapshot (not a trend): every occupation <b>posted that year</b>, positioned by how exposed its tasks are to generative AI. <b>x</b> = mean exposure score (0–1) · <b>y</b> = spread of task scores within the job · colour = exposure gradient · <b>bubble size = number of postings</b>. Pick a year to see how that year's demand sits on the exposure map.")
        _sv = load_jobs_silver()
        if _sv.empty or "date_published" not in _sv:
            st.info("Jobs silver isn't reachable here — this snapshot renders locally (and on Cloud once the jobs silver is available to the app).")
        else:
            yrs = sorted(_sv["date_published"].dt.year.dropna().astype(int).unique())
            yr = st.select_slider("Year", options=yrs, value=yrs[-1], key="exp_year") if len(yrs) > 1 else yrs[0]
            snap = chart_exposure_snapshot(_sv, int(yr))
            if snap is not None:
                plot(snap, "chart_exp_snap")
            else:
                st.info(f"No postings with exposure scores for {yr}.")
            explain(f"Each bubble is one occupation posted in {yr}; further right = more exposed to generative AI, bigger = more postings.",
                    "A yearly snapshot complements the trend charts below — it shows where that year's hiring actually sits on the AI-exposure scale.",
                    "ILO task-level exposure estimates (GPT-4 scored, expert-validated); exposure \u2260 job loss — much is augmentation, not automation.")
        st.divider()

        st.markdown("### Job demand over time")
        st.markdown("Are jobs rising or declining over time, by AI-exposure level \u2014 general market, then tech.")
        dview = st.radio("General demand view", ["By year", "Monthly (all years)"], horizontal=True, key="dview")
        if dview == "By year":
            plot(chart_demand_share(d), "chart_2")
        else:
            fig = chart_demand_month_all(load_jobs_silver())
            if fig is not None:
                plot(fig, "chart_2m")
            else:
                st.info("2026 monthly needs jobs silver on disk.")
        tview = st.radio("Tech demand view", ["By year", "Monthly (all years)"], horizontal=True, key="tview")
        if tview == "By year":
            plot(chart_tech_demand(d), "chart_3")
        else:
            tf = chart_tech_demand_month(load_tech_silver())
            if tf is not None:
                plot(tf, "chart_3m")
            else:
                st.info("Tech monthly needs tech silver on disk (data/silver/tech/dt=.../de_tech_jobs.csv).")

        st.divider()
        st.markdown("### Demand for humans who can use AI")
        st.markdown("Does the market increasingly want people who can *use* AI at work? (General jobs \u2014 tech usage isn't measurable, see note.)")
        view = st.radio("View", ["By year", "2026 monthly ramp"], horizontal=True)
        if view == "By year":
            plot(chart_usage_year(d), "chart_4")
        else:
            sv = load_jobs_silver()
            fig = chart_usage_month_2026(sv)
            if fig is not None:
                plot(fig, "chart_5")
            else:
                st.info("2026 monthly view needs the jobs silver on disk (data/silver/kaggle/dt=.../de_jobs.csv).")
        plot(chart_usage_snap(d), "chart_6")
        explain("AI-usage demand over time and the 2026 snapshot, by exposure level.",
                "Usage demand is a 2026 phenomenon, concentrated in AI-exposed roles.",
                "Pre-2026 usage \u2248 0, so the yearly line is really 2025\u21922026; monthly shows the within-2026 ramp. Small counts \u2014 read as direction.")

        st.divider()
        st.markdown("### AI-building jobs (tech)")
        st.markdown("Are 'new AI' roles \u2014 building AI/ML \u2014 growing? This is a tech phenomenon.")
        c3, c4 = st.columns(2)
        with c3:
            plot(chart_tech_building_year(d), "chart_7")
        with c4:
            plot(chart_building_snap(d), "chart_8")
        explain("AI-building demand by year and by exposure level (tech).",
                "~40\u201357% of tech roles build AI, unlike the broad market.",
                "Tech spans only 2024\u20132025; read as a level. Usage isn't measurable here (skills-field artifact).")

    with t3:
        plot(chart_merge(d), "chart_9")
        small_n_note(d["merge"], "author_class", "n_prs", "ai_agent", 1000, "PRs")
        explain("Merge rate for autonomous-agent PRs vs everyone else, within each PR-size band.",
                "The gap persists at every size \u2014 not just 'agent PRs are bigger'.",
                "Merge rate is *acceptance*, not code quality; agent PRs draw no more change-requests, pointing to process not worse code. Agent N per bucket is small.")
        if len(d["cr"]):
            st.caption("Changes-requested rate (second acceptance signal):")
            st.dataframe(d["cr"], hide_index=True, use_container_width=True)
            small_n_note(d["cr"], "pr_author_class", "n_reviews", "ai_agent", 1000, "reviews")

    with t4:
        plot(chart_churn(d), "chart_10")
        explain("How much a file is rewritten in the 14 days after an AI- vs human-touch, at equal size.",
                "The durability test: if AI code were sloppier, AI-touched files would churn more. They don't.",
                "Follow-up churn measures *activity*, not proven quality. Git-attributable AI only.")
        if len(d["ai_repo"]):
            plot(chart_repo(d), "chart_11")

    with t5:
        st.markdown("**The synthesis** \u2014 AI is entering code (adoption), the broad job market is slowly asking workers to *use* it, and tech roles increasingly *build* it. Three facets of one shift.")
        plot(chart_adoption(d), "chart_12")
        plot(chart_usage_trend(d), "chart_13")
        explain("Code-side adoption and labour-side AI-usage demand, on the same 2023\u2192 timeline.",
                "Both rising together is the thesis the project set out to test.",
                "Different sources and grains; treat as parallel trends, not a fitted correlation.")

    with t6:
        render_architecture()
        st.divider()
        render_lineage()
        st.divider()
        render_adzuna_live()
        st.divider()
        gold_downloads(d)

    with tM:
        st.markdown("### Methods & honest limitations")
        note("How each signal is built — and where to be careful reading it. The honesty is the point: every headline comes with its caveat.")
        st.markdown("#### How each signal is measured")
        st.markdown(
            "- **Code adoption** — commits carrying an AI-authorship signal (`Co-authored-by` an AI tool, a known agent author, or a self-admit phrase), de-duplicated by SHA, over total commits.\n"
            "- **PR acceptance** — closed-PR merge rate + review states, autonomous-agent vs baseline, compared *within* PR-size buckets.\n"
            "- **Durability** — 14-day follow-up churn per file-touch, by author class, again within size buckets.\n"
            "- **Jobs** — job titles → ISCO-08 via an ESCO **embedding crosswalk**; joined to **ILO** AI-exposure scores; AI-usage / AI-building tagged from title, description and skills.")
        infobox("<b>In plain language (code adoption):</b> a commit counts as ‘AI’ if it's tagged <code>Co-authored-by</code> an AI tool, authored by a known AI-agent account, or says so in the message. GH Archive replays the same commit across many events, so we keep each unique commit hash once (<b>de-dup by SHA</b>). Adoption = AI commits ÷ all commits.")
        st.markdown("#### Honest limitations")
        st.markdown(
            "- **Git-attributable AI only** — silent Copilot leaves no trace, so adoption is a **floor**, not a true level.\n"
            "- **PR quality is agent-only and small-N** — read direction, not precise rates.\n"
            "- **Churn measures activity, not proven quality** — 'reworked less' ≠ 'better', but it does contradict the 'AI is sloppier' prior.\n"
            "- **Jobs AI-usage is sparse** — emerging in 2026, so report direction. Tech 'usage' ≈ 0 is an artifact (tagged from a structured skills field).\n"
            "- **Adzuna** — short descriptions (thin AI-skill signal); some categories carry no salary.\n"
            "- **Cross-source trends are parallel, not fitted correlations** — different sources and grains.\n"
            "- **Exposure ≠ job loss** — ILO scores measure task *exposure* to generative AI; much of it is augmentation, not automation.")
        st.markdown("#### Reproducibility")
        note("Everything is versioned and rebuildable: bronze + silver in the R2 lake, gold rebuilt by <b>dbt</b> in Neon (8 models, 5 tests), orchestrated by <b>Airflow</b>. See the 🏗️ Architecture tab and the repo README for the full pipeline.")

    st.write("")
    st.markdown(
        f"<p style='color:{MUTED};font-size:12px;border-top:1px solid {GRID};padding-top:12px'>"
        f"Sources: GH Archive (code) \u00b7 Kaggle + tech job postings + Adzuna API (labour) \u00b7 ISCO-08 / ESCO / ILO reference. "
        f"Pipeline: R2 lake \u2192 Neon (dbt) \u2192 Streamlit. Gold served from Postgres."
        f"</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()