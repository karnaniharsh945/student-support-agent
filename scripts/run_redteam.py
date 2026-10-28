"""Run the compromised-model red-team lab.  Usage: python scripts/run_redteam.py"""
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ROOT, Settings          # noqa: E402
from services.redteam import run_redteam, write_redteam_report   # noqa: E402

if __name__ == "__main__":
    rep = run_redteam(replace(Settings.from_env(), model_provider="mock"))
    write_redteam_report(rep, ROOT / "reports" / "redteam_report.json")
    m = rep["metric"]
    print(f"{m['attacks_blocked']}/{m['attacks_total']} attacks blocked ({m['block_rate_pct']}%)")
    for a in rep["attacks"]:
        print(f"  {a['id']} {'BLOCKED' if a['blocked'] else 'FAIL   '} {a['title']} | {a['detail']}")
