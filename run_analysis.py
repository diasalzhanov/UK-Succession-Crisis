"""The UK Succession Crisis - full pipeline.

1. Download the free Companies House bulk files (~3 GB, first run only)
2. Build one table of every active UK private limited company + its owners' ages
3. Headline numbers, tables and charts  -> output/
4. (Optional) estimate jobs at stake from a random sample of filed accounts

Run:  python3 run_analysis.py      (or double-click "Run Analysis.command")
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- SETTINGS -------------------------------------------------------------
RUN_JOBS_ESTIMATE = True        # needs a Companies House API key (~15 min)
JOBS_SAMPLE_PER_SIZE = 150      # companies sampled per size group
DELETE_RAW_AFTER = False        # True = delete the 3 GB downloads once processed
# --------------------------------------------------------------------------

import pandas as pd  # noqa: E402

from succession import analyse  # noqa: E402
from succession.build import build  # noqa: E402
from succession.download import download_all, find_local  # noqa: E402

RAW = os.path.join(HERE, "data", "raw")
TABLE = os.path.join(HERE, "data", "processed", "companies.pkl")
OUT = os.path.join(HERE, "output")


def api_key():
    for p in (os.path.join(HERE, "api_key.txt"),
              os.path.join(HERE, "..", "Financial Screener", "api_key.txt")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                k = "".join(l.strip() for l in f if l.strip() and not l.startswith("#"))
            if k:
                return k
    return None


def main():
    print("\n=== The UK Succession Crisis ===")
    local = find_local(RAW)
    have_table = os.path.exists(TABLE)
    if have_table:
        meta = json.load(open(TABLE + ".meta.json"))
        print(f"\n[1-2/4] Using processed data from {meta['snapshot']} "
              "(delete the data/processed folder to rebuild from fresh downloads)")
        df = pd.read_pickle(TABLE)
        snap = meta["snapshot"]
    else:
        print("\n[1/4] Downloading Companies House bulk data (first run only)...")
        paths = local if all(local.values()) else download_all(RAW)
        print("\n[2/4] Building the company + owner table...")
        df = build(paths, TABLE)
        snap = df.attrs["snapshot"]
        if DELETE_RAW_AFTER:
            for p in paths.values():
                os.remove(p)

    print("\n[3/4] Crunching numbers and drawing charts...")
    summary, op = analyse.run(df, OUT, snap)
    print(f"    {summary['operating_businesses']:,} owner-managed operating businesses")
    print(f"    {summary['pct_65_plus']:.1%} have a lead owner aged 65+ "
          f"({summary['operating_owner_65_plus']:,} businesses)")
    print(f"    {summary['turning_65_next_10_years']:,} more owners turn 65 in the next 10 years")

    if RUN_JOBS_ESTIMATE:
        key = api_key()
        if not key:
            print("\n[4/4] Skipped jobs estimate: no API key (put it in api_key.txt)")
        else:
            print("\n[4/4] Estimating jobs at stake from a sample of filed accounts...")
            from succession.ch_client import CompaniesHouse
            from succession.jobs import estimate
            ch = CompaniesHouse(key, os.path.join(HERE, "data", "api_cache"))
            res = estimate(op, ch, OUT, snap, JOBS_SAMPLE_PER_SIZE)
            print(f"    ~{res['total_jobs_estimate']:,} jobs ({res['total_jobs_range_note']})")
    print(f"\nDone. Results are in: {OUT}\n")


if __name__ == "__main__":
    main()
