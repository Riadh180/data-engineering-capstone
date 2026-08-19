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

GOLD = os.environ.get("GOLD_DIR", "data/gold")
AI, ASSIST, HUMAN, BUILD = "#F0A202", "#E86A5C", "#6B7A99", "#4C9BE8"
BG, PANEL, TXT, MUTED, GRID = "#0E1117", "#161A23", "#E6E8EC", "#8B93A7", "#252A35"
BUCKET_ORDER = ["0-20", "20-100", "100-500", "500+"]

pio.templates["aiwork"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TXT, family="Inter, system-ui, sans-serif", size=13),
    xaxis=dict(gridcolor=GRID, zeroline=False), yaxis=dict(gridcolor=GRID, zeroline=False),
    margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(font_size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0)))

def base(fig, title=None, h=380):
    fig.update_layout(template="aiwork", height=h,
                      margin=dict(l=10, r=10, t=64, b=10),
                      title=dict(text=title, font=dict(size=16),
                                 y=0.97, yanchor="top", x=0.01, xanchor="left") if title else None)
    return fig

# The SINGLE data-source boundary. GOLD_BACKEND=postgres reads the warehouse;
# anything else reads the gold CSVs. Swapping backends changes nothing else.
GOLD_BACKEND = os.environ.get("GOLD_BACKEND", "csv")

_GOLD_MAP = {"adopt_year": "github_adoption_by_year",
             "adopt_month": "github_adoption_by_month",
             "jobs_band": "jobs_by_exposure_band_year",
             "merge": "github_merge_rate", "cr": "github_changes_requested",
             "churn": "github_churn_by_bucket", "ai_repo": "github_ai_share_by_repo"}

@st.cache_data
def load_gold(gold_dir=GOLD):
    if GOLD_BACKEND == "postgres":
        from sqlalchemy import create_engine
        import pandas as _pd
        u=os.environ.get("PGUSER","aiwork"); p=os.environ.get("PGPASSWORD","aiwork")
        h=os.environ.get("PGHOST","localhost"); pt=os.environ.get("PGPORT","5432")
        db=os.environ.get("PGDATABASE","aiwork")
        eng=create_engine(f"postgresql+psycopg2://{u}:{p}@{h}:{pt}/{db}")
        out={}
        for key, tbl in _GOLD_MAP.items():
            try:
                out[key]=_pd.read_sql(f"select * from gold.{tbl}", eng)
            except Exception:
                out[key]=_pd.DataFrame()
        return out
    # CSV backend (default)
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

def main():
    st.set_page_config(page_title="AI \u00d7 Work", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(f"<style>.stApp{{background:{BG};}} .block-container{{padding-top:2rem;max-width:1200px;}} h1,h2,h3{{color:{TXT};}}</style>", unsafe_allow_html=True)
    d = load_gold()
    st.title("AI \u00d7 Work")
    st.markdown(f"<p style='color:{MUTED};font-size:16px;margin-top:-8px'>How AI is reshaping code and the German job market \u2014 a bronze\u2192silver\u2192gold pipeline. Hover any chart for detail.</p>", unsafe_allow_html=True)

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
    t1, t2, t3, t4, t5 = st.tabs(["\U0001F4C8 Adoption", "\U0001F4BC Jobs", "\u2705 Acceptance", "\U0001F527 Durability", "\U0001F517 Synthesis"])

    with t1:
        st.plotly_chart(chart_adoption(d), use_container_width=True, key="chart_1")
        explain("The share of commits carrying an AI-authorship signal, each year.",
                "Clearest evidence AI is entering real codebases \u2014 with a sharp 2025 takeoff.",
                "Counts only *attributable* AI (co-author trailers + known agents); silent Copilot leaves no git trace, so this is a floor.")

    with t2:
        st.markdown("### Job demand over time")
        st.markdown("Are jobs rising or declining over time, by AI-exposure level \u2014 general market, then tech.")
        dview = st.radio("General demand view", ["By year", "Monthly (all years)"], horizontal=True, key="dview")
        if dview == "By year":
            st.plotly_chart(chart_demand_share(d), use_container_width=True, key="chart_2")
        else:
            fig = chart_demand_month_all(load_jobs_silver())
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True, key="chart_2m")
            else:
                st.info("2026 monthly needs jobs silver on disk.")
        tview = st.radio("Tech demand view", ["By year", "Monthly (all years)"], horizontal=True, key="tview")
        if tview == "By year":
            st.plotly_chart(chart_tech_demand(d), use_container_width=True, key="chart_3")
        else:
            tf = chart_tech_demand_month(load_tech_silver())
            if tf is not None:
                st.plotly_chart(tf, use_container_width=True, key="chart_3m")
            else:
                st.info("Tech monthly needs tech silver on disk (data/silver/tech/dt=.../de_tech_jobs.csv).")

        st.divider()
        st.markdown("### Demand for humans who can use AI")
        st.markdown("Does the market increasingly want people who can *use* AI at work? (General jobs \u2014 tech usage isn't measurable, see note.)")
        view = st.radio("View", ["By year", "2026 monthly ramp"], horizontal=True)
        if view == "By year":
            st.plotly_chart(chart_usage_year(d), use_container_width=True, key="chart_4")
        else:
            sv = load_jobs_silver()
            fig = chart_usage_month_2026(sv)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True, key="chart_5")
            else:
                st.info("2026 monthly view needs the jobs silver on disk (data/silver/kaggle/dt=.../de_jobs.csv).")
        st.plotly_chart(chart_usage_snap(d), use_container_width=True, key="chart_6")
        explain("AI-usage demand over time and the 2026 snapshot, by exposure level.",
                "Usage demand is a 2026 phenomenon, concentrated in AI-exposed roles.",
                "Pre-2026 usage \u2248 0, so the yearly line is really 2025\u21922026; monthly shows the within-2026 ramp. Small counts \u2014 read as direction.")

        st.divider()
        st.markdown("### AI-building jobs (tech)")
        st.markdown("Are 'new AI' roles \u2014 building AI/ML \u2014 growing? This is a tech phenomenon.")
        c3, c4 = st.columns(2)
        with c3:
            st.plotly_chart(chart_tech_building_year(d), use_container_width=True, key="chart_7")
        with c4:
            st.plotly_chart(chart_building_snap(d), use_container_width=True, key="chart_8")
        explain("AI-building demand by year and by exposure level (tech).",
                "~40\u201357% of tech roles build AI, unlike the broad market.",
                "Tech spans only 2024\u20132025; read as a level. Usage isn't measurable here (skills-field artifact).")

    with t3:
        st.plotly_chart(chart_merge(d), use_container_width=True, key="chart_9")
        explain("Merge rate for autonomous-agent PRs vs everyone else, within each PR-size band.",
                "The gap persists at every size \u2014 not just 'agent PRs are bigger'.",
                "Merge rate is *acceptance*, not code quality; agent PRs draw no more change-requests, pointing to process not worse code. Agent N per bucket is small.")
        if len(d["cr"]):
            st.caption("Changes-requested rate (second acceptance signal):")
            st.dataframe(d["cr"], hide_index=True, use_container_width=True)

    with t4:
        st.plotly_chart(chart_churn(d), use_container_width=True, key="chart_10")
        explain("How much a file is rewritten in the 14 days after an AI- vs human-touch, at equal size.",
                "The durability test: if AI code were sloppier, AI-touched files would churn more. They don't.",
                "Follow-up churn measures *activity*, not proven quality. Git-attributable AI only.")
        if len(d["ai_repo"]):
            st.plotly_chart(chart_repo(d), use_container_width=True, key="chart_11")

    with t5:
        st.markdown("**The synthesis** \u2014 AI is entering code (adoption), the broad job market is slowly asking workers to *use* it, and tech roles increasingly *build* it. Three facets of one shift.")
        st.plotly_chart(chart_adoption(d), use_container_width=True, key="chart_12")
        st.plotly_chart(chart_usage_trend(d), use_container_width=True, key="chart_13")
        explain("Code-side adoption and labour-side AI-usage demand, on the same 2023\u2192 timeline.",
                "Both rising together is the thesis the project set out to test.",
                "Different sources and grains; treat as parallel trends, not a fitted correlation.")

if __name__ == "__main__":
    main()