#!/usr/bin/env python3
"""app.py — AI x Work capstone dashboard (interactive serving layer)."""
import os
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
                      title=dict(text=title, font=dict(size=16)) if title else None)
    return fig

@st.cache_data
def load_gold(gold_dir=GOLD):
    def rd(name):
        p = os.path.join(gold_dir, name)
        return pd.read_csv(p, dtype={"isco08_4digit": str}) if os.path.exists(p) else pd.DataFrame()
    return {"adopt_year": rd("github_adoption_by_year.csv"),
            "adopt_month": rd("github_adoption_by_month.csv"),
            "jobs_band": rd("jobs_by_exposure_band_year.csv"),
            "merge": rd("github_merge_rate.csv"), "cr": rd("github_changes_requested.csv"),
            "churn": rd("github_churn_by_bucket.csv"), "ai_repo": rd("github_ai_share_by_repo.csv")}

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
        st.plotly_chart(chart_adoption(d), use_container_width=True)
        explain("The share of commits carrying an AI-authorship signal, each year.",
                "Clearest evidence AI is entering real codebases \u2014 with a sharp 2025 takeoff.",
                "Counts only *attributable* AI (co-author trailers + known agents); silent Copilot leaves no git trace, so this is a floor.")

    with t2:
        st.markdown("**Two distinct signals** \u2014 *using* AI as a tool vs *building* AI/ML systems.")
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(chart_jobs_usage(d), use_container_width=True)
        with col2:
            st.plotly_chart(chart_usage_trend(d), use_container_width=True)
        st.plotly_chart(chart_jobs_building(d), use_container_width=True)
        st.plotly_chart(chart_jobs_exposure(d), use_container_width=True)
        explain("General jobs asking for AI *usage* skills (left, by band; right, over time); tech jobs asking to *build* AI (blue); and the underlying exposure gradient.",
                "AI-usage demand is small but real in the broad market and rising 2025\u2192; building AI is a tech phenomenon (~40\u201352%). The exposure score itself is a clean monotonic gradient.",
                "General AI-usage rests on few postings per band (counts shown) \u2014 read as direction. Tech shows 0% *usage* because it's tagged from a structured skills field (frameworks), which captures *building*, not tool-use prose.")

    with t3:
        st.plotly_chart(chart_merge(d), use_container_width=True)
        explain("Merge rate for autonomous-agent PRs vs everyone else, within each PR-size band.",
                "The gap persists at every size \u2014 not just 'agent PRs are bigger'.",
                "Merge rate is *acceptance*, not code quality; agent PRs draw no more change-requests, pointing to process not worse code. Agent N per bucket is small.")
        if len(d["cr"]):
            st.caption("Changes-requested rate (second acceptance signal):")
            st.dataframe(d["cr"], hide_index=True, use_container_width=True)

    with t4:
        st.plotly_chart(chart_churn(d), use_container_width=True)
        explain("How much a file is rewritten in the 14 days after an AI- vs human-touch, at equal size.",
                "The durability test: if AI code were sloppier, AI-touched files would churn more. They don't.",
                "Follow-up churn measures *activity*, not proven quality. Git-attributable AI only.")
        if len(d["ai_repo"]):
            st.plotly_chart(chart_repo(d), use_container_width=True)

    with t5:
        st.markdown("**The synthesis** \u2014 AI is entering code (adoption), the broad job market is slowly asking workers to *use* it, and tech roles increasingly *build* it. Three facets of one shift.")
        st.plotly_chart(chart_adoption(d), use_container_width=True)
        st.plotly_chart(chart_usage_trend(d), use_container_width=True)
        explain("Code-side adoption and labour-side AI-usage demand, on the same 2023\u2192 timeline.",
                "Both rising together is the thesis the project set out to test.",
                "Different sources and grains; treat as parallel trends, not a fitted correlation.")

if __name__ == "__main__":
    main()