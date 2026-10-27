"""Streamlit front-end (presentation only - all logic lives in services/ and agent/)."""
from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from agent.llm import LLMError, build_provider
from agent.orchestrator import AgentOrchestrator
from agent.state import RequestContext
from config.settings import ConfigurationError, Settings
from database.connection import Database
from database.initialization import init_schema, seed_database
from services.container import build_services
from tools import build_registry

st.set_page_config(page_title="Student Support Agent", page_icon="🎓", layout="wide")


@st.cache_resource
def get_app():
    settings = Settings.from_env()
    db = Database(settings.database_url)
    init_schema(db)
    seed_database(db, settings.seed_path)
    svc = build_services(settings, db)
    registry = build_registry(svc)
    try:
        llm, llm_error = build_provider(settings), ""
    except ConfigurationError as e:
        llm, llm_error = None, str(e)
    orch = AgentOrchestrator(svc, llm, registry) if llm else None
    return svc, registry, orch, llm, llm_error


svc, registry, orch, llm, llm_error = get_app()

# ------------------------------------------------------------------ sidebar
st.sidebar.title("🎓 Student Support Agent")
st.sidebar.warning("Milestone 1 demo mode: no login. Pick a demo student (synthetic data).")
with svc.db.session() as s:
    from sqlalchemy import select
    from database.models import Student
    students = {st_.student_id: st_.name for st_ in s.scalars(select(Student).order_by(Student.student_id))}
student_id = st.sidebar.selectbox("Demo student", list(students), format_func=lambda k: f"{k} - {students[k]}")
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if st.sidebar.button("Start new session"):
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.pop("messages", None)
if llm is None:
    st.sidebar.error(f"LLM not configured: {llm_error}")
elif not llm.is_live:
    st.sidebar.info("Model: MOCK rule-based provider (offline demo, not a real LLM).")
else:
    st.sidebar.success(f"Model: {llm.name} / {llm.model}")
page = st.sidebar.radio("Section", ["Chat", "My memory & requests", "Traces"])
ctx = RequestContext(session_id=st.session_state.session_id, student_id=student_id)

# ------------------------------------------------------------------ chat
if page == "Chat":
    st.header("Chat")
    st.sidebar.subheader("Quick lookups (no LLM)")
    quick = None
    if st.sidebar.button("My fee status"):
        quick = "get_fee_status"
    if st.sidebar.button("My scholarship status"):
        quick = "get_scholarship_status"
    msgs = st.session_state.setdefault("messages", [])
    if quick:
        res, _ = registry.execute(quick, {}, ctx)
        msgs.append({"role": "assistant", "content": f"**{quick}** → " + (str(res.data) if res.ok else res.user_message)})
    for m in msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("meta"):
                with st.expander("Trace / evidence"):
                    st.json(m["meta"])
    prompt = st.chat_input("Ask about fees, scholarships, course changes, policies, or raise a request…")
    if prompt:
        msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        if orch is None:
            reply, meta = "The language model is not configured, so free-text chat is unavailable. Use the quick lookups.", None
        else:
            hist = [{"role": m["role"], "content": m["content"]} for m in msgs[:-1]]
            r = orch.handle_message(ctx, prompt, hist)
            reply = r.reply
            meta = {"run_id": r.run_id, "outcome": r.outcome, "tools": [t.name for t in r.tool_calls],
                    "evidence": r.evidence, "memory": r.memory_refs, "memory_events": r.memory_events,
                    "latency_ms": r.latency_ms, "tokens_in": r.input_tokens, "tokens_out": r.output_tokens}
        msgs.append({"role": "assistant", "content": reply, "meta": meta or {}})
        st.rerun()

elif page == "My memory & requests":
    st.header("Stored memory")
    items = svc.memory.list_items(student_id)
    if not items:
        st.info("Nothing remembered yet. Try: “My programme is PGDM (Big Data Analytics).”")
    for it in items:
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{it.key}**: {it.value}  \n<small>updated {it.updated_at:%Y-%m-%d %H:%M}</small>", unsafe_allow_html=True)
        if c2.button("Forget", key=f"del-{it.key}"):
            svc.memory.delete(student_id, it.key)
            st.rerun()
    st.header("Support requests")
    reqs = svc.support.list_for_student(student_id)
    st.dataframe(pd.DataFrame(reqs), use_container_width=True) if reqs else st.info("No support requests yet.")

else:
    st.header("Recent agent traces")
    rows = svc.tracer.recent(50)
    if not rows:
        st.info("No traces yet.")
    else:
        df = pd.DataFrame([{k: (", ".join(x["name"] for x in v) if k == "tool_calls" else v) for k, v in r.items()
                            if k in ("created_at", "student_id", "question", "decision", "tool_calls", "outcome", "latency_ms",
                                     "input_tokens", "output_tokens", "token_source", "provider", "error_category")} for r in rows])
        st.dataframe(df, use_container_width=True)
