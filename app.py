"""Streamlit front-end (presentation only). All authentication, authorization, approval and audit logic lives in
services/; hiding a page here is a convenience - the backend re-checks every permission on every call."""
from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import streamlit as st

from agent.llm import build_provider
from agent.orchestrator import AgentOrchestrator
from config.settings import ROOT, ConfigurationError, Settings
from database.connection import Database
from database.initialization import SchemaOutdated, init_schema, seed_database
from services.authentication import AuthenticationError
from services.authorization import AuthorizationError
from services.container import build_services
from tools import build_registry
from ui.theme import MASCOT_PATH, headline_facts, hero, inject_theme, kpis, sidebar_brand
from ui.tour import render_tour

st.set_page_config(page_title="Student Support Agent", page_icon=str(MASCOT_PATH), layout="wide")
inject_theme()


@st.cache_resource
def get_app():
    settings = Settings.from_env()
    db = Database(settings.database_url)
    try:
        init_schema(db)
    except SchemaOutdated as e:
        return None, str(e)
    seed_database(db, settings.seed_path, settings.bcrypt_rounds)
    svc = build_services(settings, db)
    registry = build_registry(svc)
    try:
        llm, llm_error = build_provider(settings), ""
    except ConfigurationError as e:
        llm, llm_error = None, str(e)
    orch = AgentOrchestrator(svc, llm, registry) if llm else None
    return dict(svc=svc, registry=registry, orch=orch, llm=llm, llm_error=llm_error), ""


app, fatal = get_app()
if app is None:
    st.error(fatal)
    st.stop()
svc, registry, orch, llm = app["svc"], app["registry"], app["orch"], app["llm"]


def table(rows, empty):
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty)


# ------------------------------------------------------------------ login gate (identity is resolved server-side)
ctx = None
token = st.session_state.get("token")
if token:
    try:
        ctx = svc.auth.context_from_token(token)
    except AuthenticationError as e:
        st.session_state.pop("token", None)
        st.warning(e.message)

if ctx is None:
    if st.session_state.get("show_tour"):
        if st.button("← Back to sign in"):
            st.session_state.show_tour = False
            st.rerun()
        render_tour()
        st.stop()
    hero("Student Support Agent", "An AI agent that uses real tools, remembers safely, protects private data, and asks a human before it changes anything. "
         "Synthetic demonstration data.", headline_facts())
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("#### What you can do")
        st.markdown("- 💬 Ask about fees, scholarships and policies\n- 🔍 Get answers backed by cited policy chunks\n- 📝 Raise support requests\n"
                    "- 🔁 Request a course change (a human approves it)\n- 🧠 Be remembered across sessions, without sharing secrets")
        if st.button("🔊 Listen to the project tour"):
            st.session_state.show_tour = True
            st.rerun()
    with right:
        with st.form("login"):
            st.markdown("#### Sign in")
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            go = st.form_submit_button("Sign in")
        if go:
            try:
                st.session_state.token = svc.auth.login(u, p)
                st.session_state.pop("messages", None)
                st.rerun()
            except AuthenticationError as e:
                st.error(e.message)
        with st.expander("Demo accounts (local testing only)"):
            st.markdown("| user | password | role |\n|---|---|---|\n| aarav | Aarav@2026 | student (S1001) |\n| diya | Diya@2026 | student (S1002) |\n"
                        "| kabir | Kabir@2026 | student (S1003) |\n| approver | Approver@2026 | approver |\n| admin | Admin@2026 | admin |")
    st.stop()

# ------------------------------------------------------------------ sidebar
sidebar_brand(ctx.username, ctx.role, f" · {ctx.student_id}" if ctx.student_id else "")
if st.sidebar.button("Log out"):
    svc.auth.logout(token)
    for k in ("token", "messages"):
        st.session_state.pop(k, None)
    st.rerun()
if llm is None:
    st.sidebar.error(f"LLM not configured: {app['llm_error']}")
elif not llm.is_live:
    st.sidebar.info("Model: MOCK rule-based provider (offline demo, not a real LLM).")
else:
    st.sidebar.success(f"Model: {llm.name} / {llm.model}")

pages = (["Chat", "My requests", "My memory", "Project tour"] if ctx.role == "student"
         else ["Approval queue", "Approval history", "Audit log", "Traces", "Evaluation", "Red-team lab", "Chat", "Project tour"])
page = st.sidebar.radio("Section", pages)

if page == "Project tour":
    render_tour()

# ------------------------------------------------------------------ student pages
elif page == "Chat":
    st.header("Chat")
    msgs = st.session_state.setdefault("messages", [])
    if ctx.role == "student":
        st.sidebar.subheader("Quick lookups (no LLM needed)")
        for label, tool in (("My fee status", "get_fee_status"), ("My scholarship status", "get_scholarship_status")):
            if st.sidebar.button(label):
                res, _ = registry.execute(tool, {}, ctx)
                msgs.append({"role": "assistant", "content": f"**{label}** — " + (json.dumps(res.data) if res.ok else res.user_message)})
    if not msgs:
        st.markdown("##### Try asking")
        ideas = (["What is my current fee status?", "The payment portal failed. Can I pay on the next working day?",
                  "I want to change my course to Machine Learning", "My programme is PGDM (Big Data Analytics)."]
                 if ctx.role == "student" else ["What is the late fee?", "How do escalations work?"])
        cols = st.columns(2)
        for i, idea in enumerate(ideas):
            if cols[i % 2].button(idea, key=f"idea-{i}", use_container_width=True):
                st.session_state.pending_prompt = idea
                st.rerun()
    for m in msgs:
        with st.chat_message(m["role"], avatar=str(MASCOT_PATH) if m["role"] == "assistant" else "🎓"):
            st.markdown(m["content"])
            if m.get("meta"):
                with st.expander("Trace · tools · evidence · authorization"):
                    st.json(m["meta"])
    prompt = st.session_state.pop("pending_prompt", None) or st.chat_input("Ask about fees, scholarships, policies, course changes, or raise a request…")
    if prompt:
        msgs.append({"role": "user", "content": prompt})
        if orch is None:
            reply, meta = "The language model is not configured, so free-text chat is unavailable. Use the quick lookups.", {}
        else:
            r = orch.handle_authenticated(token, prompt, [{"role": m["role"], "content": m["content"]} for m in msgs[:-1]])
            reply = r.reply
            meta = {"run_id": r.run_id, "outcome": r.outcome, "tools": [{"name": t.name, "ok": t.ok, "permission": t.permission} for t in r.tool_calls],
                    "evidence": r.evidence, "memory": r.memory_refs, "memory_events": r.memory_events, "latency_ms": r.latency_ms, "guards": r.guard_events,
                    "tokens_in": r.input_tokens, "tokens_out": r.output_tokens}
        msgs.append({"role": "assistant", "content": reply, "meta": meta})
        st.rerun()

elif page == "My requests":
    st.header("Support requests")
    table(svc.support.list_for_student(ctx), "No support requests yet.")
    st.header("Course-change requests (need approval)")
    mine = svc.approvals.list_for_student(ctx)
    table([{k: r[k] for k in ("display_id", "from_course", "to_course", "status", "created_at", "expires_at", "decided_by", "decision_note")} for r in mine],
          "No course-change requests. Try: “I want to change my course to Machine Learning”.")

elif page == "My memory":
    st.header("Stored memory")
    st.caption("Only non-sensitive preferences are remembered. Passwords, OTPs, keys and tokens are never stored.")
    items = svc.memory.list_items(ctx.student_id)
    if not items:
        st.info("Nothing remembered yet. Try: “My programme is PGDM (Big Data Analytics).”")
    for it in items:
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{it.key}**: {it.value}  (updated {it.updated_at:%Y-%m-%d %H:%M})")
        if c2.button("Forget", key=f"del-{it.key}"):
            svc.memory.delete(ctx.student_id, it.key)
            st.rerun()

# ------------------------------------------------------------------ approver / admin pages
elif page == "Approval queue":
    st.header("Pending approvals")
    try:
        pending = svc.approvals.list_pending(ctx)
    except AuthorizationError as e:
        st.error(e.message)
        st.stop()
    everything = svc.approvals.list_all(ctx, 500)
    kpis([("Pending now", str(len(pending))), ("Executed", str(sum(r["status"] == "EXECUTED" for r in everything))),
          ("Rejected", str(sum(r["status"] == "REJECTED" for r in everything))),
          ("Expired / stale / failed", str(sum(r["status"] in ("EXPIRED", "STALE", "FAILED") for r in everything)))])
    if not pending:
        st.info("No pending requests.")
    for r in pending:
        with st.container(border=True, key=f"apr-{r['id']}"):
            st.subheader(f"{r['display_id']} · {r['action']} · {r['student_name']} ({r['student_id']})")
            st.write(f"**Requested by:** {r['requested_by']}  ·  **Created:** {r['created_at']}  ·  **Expires:** {r['expires_at']}")
            st.write(f"**Proposed change:** {r['from_course']} → {r['to_course']}")
            st.write(f"**Reason given:** {r['reason'] or '—'}")
            st.info(f"**Consequences:** {r['consequences']}")
            risk = r["risk"]
            badge = {"LOW": "🟢", "MEDIUM": "🟠", "HIGH": "🔴"}[risk["level"]]
            st.write(f"**Risk advisor:** {badge} {risk['level']} — " + "; ".join(risk["factors"]) + f"  \n*{risk['note']}*")
            note = st.text_input("Decision note (optional)", key=f"note-{r['id']}")
            c1, c2 = st.columns(2)
            for col, label, decision in ((c1, "✅ Approve & execute", "APPROVE"), (c2, "⛔ Reject", "REJECT")):
                if col.button(label, key=f"{decision}-{r['id']}"):
                    try:
                        out = svc.approvals.decide(ctx, r["id"], decision, note)
                        (st.success if out.ok else st.warning)(out.message)
                    except AuthorizationError as e:
                        st.error(e.message)
            events = svc.audit.list_events(ctx, approval_request_id=r["id"], limit=20)
            with st.expander("Audit events for this request"):
                table(events, "none")

elif page == "Approval history":
    st.header("All approval requests")
    table(svc.approvals.list_all(ctx), "No approval requests yet.")

elif page == "Audit log":
    st.header("Audit log (append-only)")
    if st.button("🔗 Verify audit hash-chain integrity"):
        v = svc.audit.verify_chain(ctx)
        (st.success if v["ok"] else st.error)(
            f"{'Chain intact' if v['ok'] else 'TAMPERING DETECTED at event ' + str(v['first_broken_event_id'])} — "
            f"{v['checked']} events checked. Head hash: `{v['head_hash']}`")
    ev = svc.audit.list_events(ctx, limit=500)
    actions = sorted({e["action"] for e in ev})
    pick = st.multiselect("Filter by action", actions)
    rows = [{k: v for k, v in e.items() if k != "detail"} | {"detail": json.dumps(e["detail"])} for e in ev if not pick or e["action"] in pick]
    table(rows, "No audit events yet.")

elif page == "Traces":
    st.header("Recent agent traces")
    rows = svc.tracer.recent(ctx, 100)
    table([{**{k: r[k] for k in ("created_at", "user_id", "role", "student_id", "question", "decision", "outcome", "latency_ms",
                                  "input_tokens", "output_tokens", "token_source", "approval_state", "provider", "error_category")},
            "authorization": ", ".join(f"{a['tool']}:{a['permission']}" for a in r["authorization"])} for r in rows], "No traces yet.")

elif page == "Red-team lab":
    st.header("Red-team lab — what if the LLM itself is compromised?")
    st.caption("A scripted hostile model proposes attacks (cross-student reads, smuggled identity fields, injection strings, privileged tools, "
               "floods, role abuse). Each runs through the real backend; the lab checks nothing leaked, nothing changed and the denial was audited.")
    if not svc.authz.has_permission(ctx, "evaluation:read"):
        st.error("Not permitted.")
        st.stop()
    from services import redteam
    rt_file = ROOT / "reports" / "redteam_report.json"
    if svc.authz.has_permission(ctx, "evaluation:run") and st.button("Run attack catalogue now (~10 s)"):
        with st.spinner("Attacking…"):
            redteam.write_redteam_report(redteam.run_redteam(svc.settings), rt_file)
    if rt_file.exists():
        rep = json.loads(rt_file.read_text())
        m = rep["metric"]
        kpis([("Attacks blocked", f"{m['attacks_blocked']}/{m['attacks_total']}"), ("Block rate", f"{m['block_rate_pct']}%"),
              ("Categories", str(len(rep["by_category"])))])
        st.caption(m["definition"])
        table([{"id": a["id"], "category": a["category"], "attack": a["title"], "actor": a["actor"],
                "result": "BLOCKED" if a["blocked"] else "NOT BLOCKED", "detail": a["detail"]} for a in rep["attacks"]], "none")
        st.caption(rep["caveat"])
    else:
        st.info("No report yet. Run `python scripts/run_redteam.py` (or use the button as admin).")

elif page == "Evaluation":
    st.header("Evaluation results")
    if not svc.authz.has_permission(ctx, "evaluation:read"):
        st.error("Not permitted.")
        st.stop()
    if svc.authz.has_permission(ctx, "evaluation:run") and st.button("Run Assignment 2 evaluation now (mock provider, ~15 s)"):
        from services import evaluation as ev
        with st.spinner("Running…"):
            rep = ev.build_final_report(replace(svc.settings, model_provider="mock"))
            ev.write_report(rep, ROOT / "reports" / "assignment_2_final.json", "Assignment 2 - Final Evaluation")
            base = json.loads((ROOT / "reports" / "assignment_1_baseline.json").read_text())
            (ROOT / "reports" / "evaluation_comparison.md").write_text(ev.build_comparison_markdown(base, rep))
    for label, fname in (("Assignment 1 baseline", "assignment_1_baseline.json"), ("Assignment 2 final", "assignment_2_final.json")):
        f = ROOT / "reports" / fname
        if not f.exists():
            st.info(f"{label}: report not generated yet (python scripts/run_evaluation.py).")
            continue
        rep = json.loads(f.read_text())
        st.subheader(f"{label} — provider `{rep['provider']}` · commit `{rep['git_commit']}` · {rep['generated_at']}")
        st.caption(rep["note"])
        metrics = {k: v for k, v in rep["metrics"].items() if isinstance(v, dict) and "rate_pct" in v}
        table([{"metric": k, "correct/passed": v.get("correct", v.get("passed", v.get("appropriate"))), "total": v["total"], "rate %": v["rate_pct"]}
               for k, v in metrics.items()], "no metrics")
        st.write("Latency:", rep["metrics"]["latency"], "· Tokens:", rep["metrics"]["tokens"])
        with st.expander("Test cases"):
            table([{"id": c["id"], "scenario": c["name"], "result": "PASS" if c["passed"] else "FAIL", "tools": ", ".join(c["actual_tools"]) or "none",
                    "detail": c["detail"]} for c in rep["cases"]], "none")
    cmp_f = ROOT / "reports" / "evaluation_comparison.md"
    if cmp_f.exists():
        st.subheader("Baseline vs final comparison")
        st.markdown(cmp_f.read_text())
