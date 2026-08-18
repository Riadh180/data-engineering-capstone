#!/usr/bin/env python3
"""app.py — AI x Work capstone dashboard (interactive serving layer)."""
import os
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

GOLD = os.environ.get("GOLD_DIR", "data/gold")
AI, ASSIST, HUMAN = "#F0A202", "#E86A5C", "#6B7A99"
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

def chart_jobs(d, dataset):
    b = d["jobs_band"]; b = b[b.dataset == dataset]
    g = (b.groupby(["exposure_order", "exposure_category"])
           .agg(postings=("n_postings","sum"), ai=("ai_skill_rate","mean"), exp=("avg_exposure","mean"))
           .reset_index().sort_values("exposure_order"))
    fig = go.Figure(go.Bar(
        x=g.ai*100, y=g.exposure_category, orientation="h",
        marker=dict(color=g.exp, colorscale=[[0, HUMAN], [1, AI]], showscale=False),
        text=[f"{v:.1f}%  (n={n:,})" for v, n in zip(g.ai*100, g.postings)],
        textposition="outside", textfont=dict(color=TXT),
        hovertemplate="<b>%{y}</b><br>AI-skill demand: %{x:.1f}%<br>avg exposure: %{customdata:.2f}<extra></extra>",
        customdata=g.exp))
    fig.update_xaxes(title="AI-skill demand (%)")
    return base(fig, f"AI-skill demand by exposure band \u2014 {dataset}")

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
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% AI touches<br>%{customdata[0]:,} of %{customdata[1]:,}<extra></extra>",
        customdata=r[["ai_touches", "touches"]].values))
    fig.update_xaxes(title="AI share of file-touches (%)")
    return base(fig, "AI adoption varies by repo", h=260)

def chart_overlay(d):
    a = d["adopt_year"].sort_values("year")
    jb = d["jobs_band"]; jb = jb[jb.dataset == "general"] if "dataset" in jb else jb
    jy = (jb.groupby("year").apply(lambda g:(g.ai_skill_rate*g.n_postings).sum()/g.n_postings.sum())
          .reset_index(name="ai_skill_rate"))
    fig = go.Figure()
    fig.add_scatter(x=a.year.astype(str), y=a.ai_share_pct, name="AI in code (%)",
                    mode="lines+markers", line=dict(color=AI, width=3), marker=dict(size=10), yaxis="y1",
                    hovertemplate="%{x}: %{y:.4f}% of commits<extra></extra>")
    fig.add_scatter(x=jy.year.astype(str), y=jy.ai_skill_rate*100, name="AI-skill demand in jobs (%)",
                    mode="lines+markers", line=dict(color=HUMAN, width=3, dash="dot"),
                    marker=dict(size=10, symbol="square"), yaxis="y2",
                    hovertemplate="%{x}: %{y:.2f}% of postings<extra></extra>")
    fig.update_layout(
        yaxis=dict(title=dict(text="AI in code (%)", font=dict(color=AI)), tickfont=dict(color=AI)),
        yaxis2=dict(title=dict(text="AI-skill demand (%)", font=dict(color=HUMAN)),
                    tickfont=dict(color=HUMAN), overlaying="y", side="right"))
    return base(fig, "AI in code vs AI-skill demand in jobs")

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
    if len(d["merge"]):
        mm = d["merge"].groupby("author_class").apply(lambda g:(g.merged_rate*g.n_prs).sum()/g.n_prs.sum())
        if {"ai_agent","baseline"}.issubset(mm.index):
            kpi(c2, "Agent PR merge gap", f"{(mm['baseline']-mm['ai_agent'])*100:.0f} pts", "agent PRs accepted less, size-controlled")
    if len(d["cr"]):
        g = d["cr"].set_index("pr_author_class").changes_requested_rate
        if {"ai_agent","baseline"}.issubset(g.index):
            kpi(c3, "Change-requests", "\u2248 equal", f"agent {g['ai_agent']*100:.1f}% vs human {g['baseline']*100:.1f}%")
    if len(d["ai_repo"]):
        kpi(c4, "AI share by repo", f"{d['ai_repo'].ai_pct.min():.0f}\u2013{d['ai_repo'].ai_pct.max():.0f}%", "varies widely across projects")
    st.write("")
    t1, t2, t3, t4, t5 = st.tabs(["\U0001F4C8 Adoption", "\U0001F4BC Jobs", "\u2705 Acceptance", "\U0001F527 Durability", "\U0001F517 Synthesis"])
    with t1:
        st.plotly_chart(chart_adoption(d), use_container_width=True)
        explain("The share of commits carrying an AI-authorship signal, each year.",
                "Clearest evidence AI is entering real codebases \u2014 and it shows *when* (a sharp 2025 takeoff).",
                "Counts only *attributable* AI (co-author trailers + known agent accounts); silent Copilot use leaves no git trace, so this is a floor.")
    with t2:
        ds = st.radio("Dataset", ["general", "tech"], horizontal=True, help="general = broad labour market; tech = tech roles only")
        st.plotly_chart(chart_jobs(d, ds), use_container_width=True)
        explain("AI-skill demand across occupations, grouped by AI-exposure band.",
                "Tests whether the jobs most exposed to AI are the ones now asking for AI skills.",
                "General-dataset AI-skill mentions are sparse (counts shown) \u2014 read as direction. Bars shaded by avg exposure.")
    with t3:
        st.plotly_chart(chart_merge(d), use_container_width=True)
        explain("Merge rate for autonomous-agent PRs vs everyone else, within each PR-size band.",
                "The gap persists at every size, so it isn't just 'agent PRs are bigger' \u2014 a real acceptance difference.",
                "Merge rate is *acceptance*, not code quality \u2014 and agent PRs draw no more change-requests (below), pointing to process not worse code. Agent N is small.")
        if len(d["cr"]):
            st.caption("Changes-requested rate (second acceptance signal):")
            st.dataframe(d["cr"], hide_index=True, use_container_width=True)
    with t4:
        st.plotly_chart(chart_churn(d), use_container_width=True)
        explain("How much a file is rewritten in the 14 days after an AI- vs human-touch, at equal change size.",
                "The durability test: if AI code were sloppier, AI-touched files would churn more. They don't.",
                "Follow-up churn measures *activity*, not proven quality. Git-attributable AI only.")
        if len(d["ai_repo"]):
            st.plotly_chart(chart_repo(d), use_container_width=True)
    with t5:
        st.plotly_chart(chart_overlay(d), use_container_width=True)
        explain("Both pillars on one timeline: AI adoption in code (left) and AI-skill demand in jobs (right).",
                "The synthesis the project builds toward \u2014 code adoption and labour demand rising together.",
                "Overlap is limited (jobs mostly 2025\u201326, code 2023\u201325) \u2014 read as two trends meeting, not a tight correlation.")

if __name__ == "__main__":
    main()