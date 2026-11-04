"""Global look and feel: forest green on warm off-white. One place to change the design."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Sans+Telugu:wght@400;600&family=Noto+Sans+Kannada:wght@400;600&display=swap');

:root {
  --gs-green: #1F5D3A; --gs-green-dark: #174A2E; --gs-sage: #A9C1AE; --gs-sage-soft: #E7EFE8;
  --gs-bg: #FAF7F0; --gs-card: #FFFFFF; --gs-border: #E6E1D6;
  --gs-text: #1F2A24; --gs-muted: #66756B;
  --gs-amber: #9A6A12; --gs-amber-bg: #FBF1DC;
  --gs-red: #9B3B3B; --gs-red-bg: #F8E6E4;
  --gs-blue: #2F5D7C; --gs-blue-bg: #E4EEF5;
}

html, body, .stApp, [class*="css"] {
  font-family: "Inter", "Noto Sans Devanagari", "Noto Sans Telugu", "Noto Sans Kannada", "Nirmala UI", system-ui, sans-serif;
  color: var(--gs-text);
}
.stApp { background: var(--gs-bg); }
header[data-testid="stHeader"] { background: transparent; }
footer { visibility: hidden; }
.block-container { max-width: 1120px; padding-top: 2.2rem; padding-bottom: 4rem; }
h1, h2, h3, h4 { letter-spacing: -0.01em; color: var(--gs-text); }
[data-testid="stHeaderActionElements"] { display: none; }
h3 { font-size: 1.15rem !important; font-weight: 600 !important; }

/* sidebar */
section[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--gs-border); }
section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
.gs-brand { display:flex; align-items:center; gap:.65rem; margin-bottom:1.4rem; }
.gs-brand-mark { width:36px; height:36px; border-radius:10px; background:var(--gs-green); color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:1.05rem; }
.gs-brand-name { font-weight:700; font-size:1.1rem; line-height:1.1; }
.gs-brand-sub { font-size:.72rem; color:var(--gs-muted); }
a[data-testid="stPageLink-NavLink"] { border-radius:10px; padding:.5rem .75rem; margin-bottom:2px; color:var(--gs-text); }
a[data-testid="stPageLink-NavLink"]:hover { background: var(--gs-sage-soft); }
a[data-testid="stPageLink-NavLink"][aria-current="page"] { background: var(--gs-sage-soft); color: var(--gs-green-dark);
  font-weight:600; box-shadow: inset 3px 0 0 var(--gs-green); }
.gs-profile { display:flex; align-items:center; gap:.65rem; padding:.7rem; border:1px solid var(--gs-border);
  border-radius:12px; margin:1rem 0 .6rem; background: var(--gs-bg); }
.gs-avatar { width:34px; height:34px; border-radius:50%; background:var(--gs-sage); color:var(--gs-green-dark);
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.85rem; flex:none; }
.gs-profile-name { font-weight:600; font-size:.9rem; line-height:1.2; }
.gs-profile-mail { font-size:.72rem; color:var(--gs-muted); overflow:hidden; text-overflow:ellipsis; max-width:150px; }

/* cards: bordered containers and forms */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"]),
div[data-testid="stForm"] {
  background: var(--gs-card); border: 1px solid var(--gs-border) !important; border-radius: 14px !important;
  box-shadow: 0 1px 2px rgba(31,42,36,.04);
}

/* buttons */
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {
  border-radius: 10px; font-weight: 500; border: 1px solid var(--gs-border); padding: .45rem 1rem;
}
.stButton > button[kind="primary"], div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: var(--gs-green); border-color: var(--gs-green); color: #fff;
}
.stButton > button[kind="primary"]:hover, div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
  background: var(--gs-green-dark); border-color: var(--gs-green-dark);
}
.stButton > button:focus-visible { outline: 3px solid var(--gs-sage); }

/* page header */
.gs-eyebrow { text-transform: uppercase; letter-spacing:.08em; font-size:.72rem; font-weight:600; color: var(--gs-green); }
.gs-title { font-size: 1.85rem; font-weight: 700; margin: .1rem 0 .25rem; letter-spacing:-0.02em; line-height:1.25; }
.gs-subtitle { color: var(--gs-muted); font-size: 1rem; margin-bottom: 1.4rem; max-width: 46rem; }

/* stat cards */
.gs-stat { background: var(--gs-card); border:1px solid var(--gs-border); border-radius:14px; padding:1rem 1.15rem;
  box-shadow: 0 1px 2px rgba(31,42,36,.04); }
.gs-stat-label { color: var(--gs-muted); font-size:.82rem; font-weight:500; }
.gs-stat-value { font-size:2rem; font-weight:700; line-height:1.15; margin-top:.1rem; }
.gs-stat-hint { color: var(--gs-muted); font-size:.78rem; margin-top:.15rem; }
.gs-stat.tone-amber .gs-stat-value { color: var(--gs-amber); }
.gs-stat.tone-green .gs-stat-value { color: var(--gs-green); }

/* chips */
.gs-chip { display:inline-block; padding:.15rem .6rem; border-radius:999px; font-size:.75rem; font-weight:600;
  border:1px solid transparent; white-space:nowrap; }
.gs-chip.neutral { background:#EEEBE2; color:#5A655E; }
.gs-chip.green { background: var(--gs-sage-soft); color: var(--gs-green-dark); border-color: var(--gs-sage); }
.gs-chip.amber { background: var(--gs-amber-bg); color: var(--gs-amber); }
.gs-chip.red { background: var(--gs-red-bg); color: var(--gs-red); }
.gs-chip.blue { background: var(--gs-blue-bg); color: var(--gs-blue); }

/* callouts */
.gs-callout { border-radius:12px; padding:.85rem 1.05rem; margin:.4rem 0 1rem; border:1px solid; font-size:.92rem; line-height:1.5; }
.gs-callout b { display:block; margin-bottom:.1rem; }
.gs-callout.info { background: var(--gs-blue-bg); border-color:#C9DCEA; color:#244A63; }
.gs-callout.warn { background: var(--gs-amber-bg); border-color:#EBD6A6; color:#6F4C0C; }
.gs-callout.ok { background: var(--gs-sage-soft); border-color: var(--gs-sage); color: var(--gs-green-dark); }

/* empty state */
.gs-empty { text-align:center; padding:2.4rem 1rem; background:var(--gs-card); border:1px dashed var(--gs-sage);
  border-radius:14px; margin-bottom:1rem; }
.gs-empty h4 { margin:0 0 .3rem; }
.gs-empty p { color: var(--gs-muted); margin:0; }

/* transcript segments */
.gs-seg { background:var(--gs-card); border:1px solid var(--gs-border); border-left:4px solid var(--gs-sage);
  border-radius:10px; padding:.7rem 1rem; margin:.45rem 0; }
.gs-seg-meta { display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; font-size:.78rem; color:var(--gs-muted); margin-bottom:.3rem; }
.gs-seg-id { font-weight:700; color: var(--gs-green); }
.gs-seg-text { font-size:1.03rem; line-height:1.65; }

/* decisions */
.gs-item { border:1px solid var(--gs-border); border-left:4px solid var(--gs-sage); border-radius:10px;
  padding:.75rem 1rem; margin:.45rem 0; background:var(--gs-card); }
.gs-item.approved { border-left-color: var(--gs-green); background:#F6FAF6; }
.gs-item.proposed { border-left-color: #D9A441; background:#FFFBF1; }
.gs-item.rejected { border-left-color: #C46A6A; background:#FFF8F7; }
.gs-item-title { font-weight:600; margin:.25rem 0 0; line-height:1.5; }
.gs-item-meta { color:var(--gs-muted); font-size:.84rem; margin-top:.25rem; }

/* steps */
.gs-step { display:flex; gap:.8rem; align-items:center; margin-bottom:.4rem; }
.gs-step-num { width:28px; height:28px; border-radius:50%; background:var(--gs-green); color:#fff; font-weight:700;
  font-size:.85rem; display:flex; align-items:center; justify-content:center; flex:none; }
.gs-step-num.done { background: var(--gs-sage); color: var(--gs-green-dark); }
.gs-step-title { font-weight:600; font-size:1.05rem; }
.gs-flow { display:flex; gap:.5rem; flex-wrap:wrap; margin:.2rem 0 1rem; }
.gs-flow span { font-size:.8rem; padding:.2rem .7rem; border-radius:999px; background:#EEEBE2; color:#5A655E; }
.gs-flow span.done { background: var(--gs-sage-soft); color: var(--gs-green-dark); font-weight:600; }

.gs-meeting-meta + .gs-chip { margin-bottom: .7rem; }
.gs-meeting-title { font-weight:600; font-size:1.05rem; line-height:1.3; }
.gs-meeting-meta { color:var(--gs-muted); font-size:.85rem; margin:.15rem 0 .5rem; }
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
