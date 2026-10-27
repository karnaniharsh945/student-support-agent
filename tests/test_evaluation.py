from services import evaluation as ev


def test_assignment1_suite_runs_and_scores(env):
    report = ev.build_report("test", ev.A1_CASES, env.settings)
    m = report["metrics"]
    assert m["task_success"]["total"] == 11
    failed = [c["id"] for c in report["cases"] if "task" in c["tags"] and not c["passed"]]
    assert failed == []
    assert m["tokens"]["input_total"] is None          # mock reports no tokens -> must say unavailable
    assert m["latency"]["n"] > 0
    assert all(c["traces"] for c in report["cases"])


def test_baseline_probe_documents_missing_isolation(env):
    out = ev.a1_probe_cross_student(env)
    assert out.extra["leaked"] is True     # Milestone 1 has no authorization - documented limitation


def test_report_writing(env, tmp_path):
    report = ev.build_report("t", ev.A1_CASES[:2], env.settings)
    ev.write_report(report, tmp_path / "r.json", "T")
    assert (tmp_path / "r.json").exists() and "Trace table" in (tmp_path / "r.md").read_text()
