"""Run the evaluation suite and write reports.   Usage: python scripts/run_evaluation.py --provider mock|env"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ROOT, Settings          # noqa: E402
from services import evaluation as ev               # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock", help="'mock' (offline, deterministic) or 'env' (use MODEL_PROVIDER from .env)")
    ap.add_argument("--assignment", choices=["1", "2"], default="1")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    settings = Settings.from_env()
    if a.provider == "mock":
        settings = replace(settings, model_provider="mock")
    if a.assignment == "1":
        out = Path(a.out or ROOT / "reports" / "assignment_1_baseline.json")
        report = ev.build_report("Assignment 1 baseline", ev.A1_CASES, settings)
        ev.write_report(report, out, "Assignment 1 - Baseline Evaluation")
    else:
        out = Path(a.out or ROOT / "reports" / "assignment_2_final.json")
        report = ev.build_final_report(settings)
        ev.write_report(report, out, "Assignment 2 - Final Evaluation")
        baseline = json.loads((ROOT / "reports" / "assignment_1_baseline.json").read_text())
        (out.parent / "evaluation_comparison.md").write_text(ev.build_comparison_markdown(baseline, report))
    m = report["metrics"]
    print(f"provider={report['provider']}  task_success={m['task_success']}  tool_selection={m['tool_selection']}")
    for k in ("unauthorized_access_prevention", "approval_enforcement", "rejection_enforcement", "memory_privacy"):
        if k in m:
            print(f"  {k}: {m[k]}")
    for c in report["cases"]:
        print(f"  {c['id']:8} {'PASS' if c['passed'] else 'FAIL'}  {c['name']}  | {c['detail']}")


if __name__ == "__main__":
    main()
