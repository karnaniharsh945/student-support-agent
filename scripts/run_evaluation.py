"""Run the evaluation suite and write reports.   Usage: python scripts/run_evaluation.py --provider mock|env"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ROOT, Settings          # noqa: E402
from services import evaluation as ev               # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock", help="'mock' (offline, deterministic) or 'env' (use MODEL_PROVIDER from .env)")
    ap.add_argument("--out", default=str(ROOT / "reports" / "assignment_1_baseline.json"))
    a = ap.parse_args()
    settings = Settings.from_env()
    if a.provider == "mock":
        settings = replace(settings, model_provider="mock")
    report = ev.build_report("Assignment 1 baseline", ev.A1_CASES, settings)
    ev.write_report(report, Path(a.out), "Assignment 1 - Baseline Evaluation")
    m = report["metrics"]
    print(f"provider={report['provider']}  task_success={m['task_success']}  tool_selection={m['tool_selection']}")
    for c in report["cases"]:
        print(f"  {c['id']:8} {'PASS' if c['passed'] else 'FAIL'}  {c['name']}  | {c['detail']}")


if __name__ == "__main__":
    main()
