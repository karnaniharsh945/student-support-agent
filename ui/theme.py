"""Visual theme: animated cat background, glass panels, gradient accents. Presentation only (no business logic)."""
from __future__ import annotations

import base64
import json
import random
from functools import lru_cache
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MASCOT_PATH = ASSETS / "cat_mascot.png"


@lru_cache(maxsize=1)
def _b64(name: str) -> str:
    return base64.b64encode((ASSETS / name).read_bytes()).decode("ascii")


def mascot_uri() -> str:
    return "data:image/png;base64," + _b64("cat_mascot.png")


def _particles(n: int = 28) -> str:
    rnd = random.Random(7)                        # deterministic layout
    spans = []
    for _ in range(n):
        size = rnd.choice((3, 4, 5, 6, 8))
        spans.append(f'<i style="left:{rnd.randint(1, 99)}%;width:{size}px;height:{size}px;'
                     f'animation-duration:{rnd.randint(14, 34)}s;animation-delay:-{rnd.randint(0, 30)}s;'
                     f'opacity:{rnd.choice((.25, .4, .55))}"></i>')
    return "".join(spans)


_CSS = """
<style>
:root{--ink:#eef1ff;--muted:#a9b2d6;--glass:rgba(16,22,48,.58);--glass2:rgba(26,34,70,.55);--line:rgba(160,175,255,.20);
--a1:#8b7bff;--a2:#34d4ff;--a3:#ff7ad9;--ok:#46e3a0;--warn:#ffc857;--bad:#ff6b8a}
html,body{background:#060913 !important}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:transparent !important}
[data-testid="stHeader"]{background:transparent !important}
[data-testid="stAppViewContainer"],[data-testid="stSidebar"]{position:relative;z-index:1}

/* ---------- animated background (fixed, behind everything) ---------- */
.ssa-bg{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none;background:#060913}
.ssa-cat{position:absolute;inset:-6%;background:url(__CAT__) 55% 38%/cover no-repeat;filter:blur(5px) brightness(.5) saturate(1.3);
  transform-origin:58% 36%;animation:kenburns 42s ease-in-out infinite alternate}
@keyframes kenburns{0%{transform:scale(1.05) translate3d(-1.5%,0,0)}50%{transform:scale(1.16) translate3d(1.2%,-1.4%,0)}100%{transform:scale(1.24) translate3d(2%,1.2%,0)}}
.ssa-aurora{position:absolute;width:62vmax;height:62vmax;border-radius:50%;filter:blur(70px);mix-blend-mode:screen;opacity:.42;will-change:transform}
.ssa-aurora.a1{background:radial-gradient(circle,#6a5cff 0%,transparent 66%);left:-18vmax;top:-20vmax;animation:drift1 26s ease-in-out infinite alternate}
.ssa-aurora.a2{background:radial-gradient(circle,#18c8ff 0%,transparent 66%);right:-22vmax;top:8vmax;animation:drift2 32s ease-in-out infinite alternate}
.ssa-aurora.a3{background:radial-gradient(circle,#ff5fd0 0%,transparent 66%);left:18vmax;bottom:-30vmax;animation:drift3 36s ease-in-out infinite alternate;opacity:.30}
@keyframes drift1{to{transform:translate(18vmax,14vmax) scale(1.2)}}
@keyframes drift2{to{transform:translate(-16vmax,18vmax) scale(.9)}}
@keyframes drift3{to{transform:translate(14vmax,-12vmax) scale(1.15)}}
.ssa-grid{position:absolute;inset:0;background-image:linear-gradient(rgba(140,160,255,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(140,160,255,.07) 1px,transparent 1px);
  background-size:56px 56px;-webkit-mask-image:radial-gradient(ellipse at 50% 30%,#000 15%,transparent 72%);mask-image:radial-gradient(ellipse at 50% 30%,#000 15%,transparent 72%);
  animation:gridmove 22s linear infinite}
@keyframes gridmove{to{background-position:0 56px,56px 0}}
.ssa-vignette{position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 38%,rgba(4,6,14,.78) 100%)}
.ssa-bg i{position:absolute;bottom:-12px;border-radius:50%;background:radial-gradient(circle,#fff,#9fb0ff 60%,transparent 70%);animation:floatup linear infinite}
@keyframes floatup{0%{transform:translate3d(0,0,0)}50%{transform:translate3d(30px,-55vh,0)}100%{transform:translate3d(-20px,-112vh,0)}}

/* hide Streamlit chrome we don't need */
[data-testid="stAppDeployButton"],.stAppDeployButton,[data-testid="stToolbar"] [data-testid="stAppDeployButton"]{display:none !important}
#MainMenu{visibility:hidden}footer{visibility:hidden}
/* long button labels wrap instead of truncating */
.stButton>button p{white-space:normal !important;line-height:1.25}
.stButton>button{min-height:3.1rem;height:auto}
[data-testid="stChatMessageAvatarUser"]{background:linear-gradient(135deg,#8b7bff,#34d4ff) !important;border-radius:50% !important}

/* ---------- typography ---------- */
h1,h2,h3,[data-testid="stHeading"]{letter-spacing:-.02em}
h1{background:linear-gradient(92deg,#fff 10%,#b9b1ff 45%,#6fe3ff 85%);-webkit-background-clip:text;background-clip:text;color:transparent !important}
[data-testid="stCaptionContainer"],.stCaption{color:var(--muted) !important}

/* ---------- glass surfaces ---------- */
[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(14,19,44,.86),rgba(10,14,34,.80)) !important;backdrop-filter:blur(18px) saturate(1.4);border-right:1px solid var(--line)}
[data-testid="stSidebar"] *{color:var(--ink)}
[class*="st-key-apr-"]{background:rgba(12,17,40,.82) !important;border:1px solid var(--line) !important;border-radius:20px !important;backdrop-filter:blur(18px);
  box-shadow:0 14px 44px rgba(2,4,20,.55);padding:.5rem .8rem}
[data-testid="stExpander"],[data-testid="stForm"],div[data-testid="stMetric"],[data-testid="stAlert"]{
  background:var(--glass) !important;border:1px solid var(--line) !important;border-radius:18px !important;backdrop-filter:blur(14px);box-shadow:0 10px 38px rgba(2,4,20,.45)}
[data-testid="stExpander"] summary{font-weight:600}
[data-testid="stForm"]{padding:1.4rem 1.4rem .6rem}
div[data-testid="stMetric"]{padding:.9rem 1.1rem}
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;border:1px solid var(--line)}

/* ---------- inputs & buttons ---------- */
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:rgba(8,12,30,.72) !important;border:1px solid var(--line) !important;border-radius:12px !important;color:var(--ink) !important}
[data-testid="stTextInput"] input:focus{border-color:var(--a1) !important;box-shadow:0 0 0 3px rgba(139,123,255,.28) !important}
.stButton>button,[data-testid="stFormSubmitButton"]>button{background:linear-gradient(120deg,var(--a1),#5b8cff 55%,var(--a2));color:#fff !important;border:0;border-radius:12px;font-weight:650;
  padding:.55rem 1.1rem;box-shadow:0 8px 24px rgba(91,110,255,.38);transition:transform .18s ease,box-shadow .18s ease,filter .18s ease}
.stButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(91,110,255,.55);filter:brightness(1.08)}
.stButton>button:active{transform:translateY(0) scale(.98)}
[data-testid="stSidebar"] .stButton>button{background:rgba(139,123,255,.16);box-shadow:none;border:1px solid var(--line);width:100%;text-align:left}
[data-testid="stSidebar"] .stButton>button:hover{background:rgba(139,123,255,.34)}
[data-testid="stSidebar"] [role="radiogroup"] label{padding:.35rem .6rem;border-radius:10px;transition:background .15s}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:rgba(139,123,255,.18)}

/* ---------- chat ---------- */
[data-testid="stChatMessage"]{background:var(--glass) !important;border:1px solid var(--line);border-radius:18px;padding:.9rem 1.1rem;backdrop-filter:blur(12px);
  box-shadow:0 8px 28px rgba(2,4,20,.40);animation:rise .45s cubic-bezier(.2,.8,.2,1) both}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){background:linear-gradient(135deg,rgba(110,92,255,.50),rgba(40,150,255,.34)) !important}
@keyframes rise{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
[data-testid="stChatInput"]{background:var(--glass2) !important;border:1px solid var(--line);border-radius:18px;backdrop-filter:blur(14px)}
[data-testid="stBottom"] > div{background:transparent !important}
[data-testid="stChatMessageAvatarAssistant"] img{border-radius:50%;box-shadow:0 0 0 2px rgba(139,123,255,.7),0 0 18px rgba(139,123,255,.5)}

/* ---------- custom components ---------- */
.ssa-hero{display:flex;gap:1.6rem;align-items:center;padding:.4rem .2rem 1rem}
.ssa-mascot{width:150px;height:150px;border-radius:50%;flex:none;position:relative;animation:bob 5s ease-in-out infinite;
  box-shadow:0 0 0 4px rgba(255,255,255,.08),0 0 52px rgba(139,123,255,.60)}
.ssa-mascot::before{content:"";position:absolute;inset:-6px;border-radius:50%;background:conic-gradient(from 0deg,#8b7bff,#34d4ff,#ff7ad9,#8b7bff);z-index:-1;animation:spin 7s linear infinite;filter:blur(1px)}
.ssa-mascot img{width:100%;height:100%;border-radius:50%;display:block;object-fit:cover}
@keyframes bob{50%{transform:translateY(-9px) rotate(-1.5deg)}}
@keyframes spin{to{transform:rotate(360deg)}}
.ssa-title{font-size:2.7rem;font-weight:800;line-height:1.05;letter-spacing:-.03em;margin:0;
  background:linear-gradient(92deg,#fff 5%,#c5bcff 45%,#72e6ff 90%);-webkit-background-clip:text;background-clip:text;color:transparent}
.ssa-sub{color:var(--muted);font-size:1.06rem;margin:.45rem 0 0;max-width:36rem}
.ssa-chips{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0 .2rem}
.ssa-chip{padding:.38rem .8rem;border-radius:999px;font-size:.84rem;font-weight:600;background:rgba(139,123,255,.16);border:1px solid var(--line);color:#dfe4ff;
  backdrop-filter:blur(8px);animation:chip 3.6s ease-in-out infinite}
.ssa-chip:nth-child(2n){animation-delay:-1.2s}.ssa-chip:nth-child(3n){animation-delay:-2.2s}
@keyframes chip{50%{transform:translateY(-3px);box-shadow:0 8px 22px rgba(139,123,255,.28)}}
.ssa-side-brand{display:flex;align-items:center;gap:.7rem;margin:.2rem 0 .6rem}
.ssa-side-brand img{width:46px;height:46px;border-radius:50%;box-shadow:0 0 0 2px rgba(139,123,255,.7),0 0 20px rgba(139,123,255,.55);animation:bob 5s ease-in-out infinite}
.ssa-side-brand b{font-size:1.05rem;letter-spacing:-.01em}
.ssa-role{display:inline-block;padding:.12rem .6rem;border-radius:999px;font-size:.76rem;font-weight:700;background:linear-gradient(120deg,var(--a1),var(--a2));color:#fff}
.ssa-card{background:var(--glass);border:1px solid var(--line);border-radius:18px;padding:1rem 1.2rem;backdrop-filter:blur(14px);box-shadow:0 10px 36px rgba(2,4,20,.45);margin-bottom:.8rem}
.ssa-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin:.4rem 0 1rem}
.ssa-kpi{background:var(--glass);border:1px solid var(--line);border-radius:16px;padding:.8rem 1rem;backdrop-filter:blur(12px)}
.ssa-kpi b{display:block;font-size:1.55rem;background:linear-gradient(92deg,#fff,#9fe9ff);-webkit-background-clip:text;background-clip:text;color:transparent}
.ssa-kpi span{color:var(--muted);font-size:.82rem}
@media (max-width:760px){.ssa-hero{flex-direction:column;text-align:center}.ssa-title{font-size:2rem}}
@media (prefers-reduced-motion:reduce){.ssa-bg *,.ssa-mascot,.ssa-chip,.ssa-side-brand img,[data-testid="stChatMessage"]{animation:none !important}}
</style>
"""


def inject_theme() -> None:
    css = _CSS.replace("__CAT__", "data:image/jpeg;base64," + _b64("cat_bg.jpg"))
    bg = ('<div class="ssa-bg"><div class="ssa-cat"></div><div class="ssa-aurora a1"></div><div class="ssa-aurora a2"></div>'
          '<div class="ssa-aurora a3"></div><div class="ssa-grid"></div>' + _particles() + '<div class="ssa-vignette"></div></div>')
    st.markdown(css + bg, unsafe_allow_html=True)


def hero(title: str, subtitle: str, chips: list[str]) -> None:
    chips_html = "".join(f'<span class="ssa-chip">{c}</span>' for c in chips)
    st.markdown(f'<div class="ssa-hero"><div class="ssa-mascot"><img src="{mascot_uri()}" alt="mascot"></div>'
                f'<div><h1 class="ssa-title">{title}</h1><p class="ssa-sub">{subtitle}</p><div class="ssa-chips">{chips_html}</div></div></div>',
                unsafe_allow_html=True)


def sidebar_brand(name: str, role: str, extra: str = "") -> None:
    st.sidebar.markdown(f'<div class="ssa-side-brand"><img src="{mascot_uri()}"><div><b>Student Support Agent</b><br>'
                        f'<span class="ssa-role">{role}</span> <span style="color:#a9b2d6;font-size:.82rem">{name}{extra}</span></div></div>',
                        unsafe_allow_html=True)


def kpis(items: list[tuple[str, str]]) -> None:
    st.markdown('<div class="ssa-kpis">' + "".join(f'<div class="ssa-kpi"><b>{v}</b><span>{k}</span></div>' for k, v in items) + "</div>",
                unsafe_allow_html=True)


def headline_facts() -> list[str]:
    """Chips for the hero, taken from the generated reports when they exist (never hard-coded claims)."""
    chips = ["🧠 privacy-safe memory", "👤 human-approved changes", "🔗 hash-chained audit log"]
    f = ROOT / "reports" / "redteam_report.json"
    if f.exists():
        m = json.loads(f.read_text())["metric"]
        chips.insert(0, f"🛡️ {m['attacks_blocked']}/{m['attacks_total']} red-team attacks blocked")
    return chips
