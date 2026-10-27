"""Create tables and load synthetic seed data.  Usage: python scripts/initialize_database.py [--reset]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings                                   # noqa: E402
from database.connection import Database                               # noqa: E402
from database.initialization import init_schema, reset_schema, seed_database   # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="DROP all tables first (demo data only!)")
    a = ap.parse_args()
    s = Settings.from_env()
    db = Database(s.database_url)
    (reset_schema if a.reset else init_schema)(db)
    seed_database(db, s.seed_path)
    print(f"Database ready at {s.database_url}")


if __name__ == "__main__":
    main()
