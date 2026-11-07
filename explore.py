"""YOUR OWN ANALYSIS - change the settings below, save, then double-click "Explore.command".

Ask your own question of the data. Examples:
  - What if retirement age is 70 instead of 65?     -> AGE_CUTOFF = 70
  - How exposed is manufacturing in each region?   -> SECTOR = "Manufacturing"
  - Which industries are most exposed in Wales?    -> REGION = "Wales"
  - What about medium & large firms only?          -> SIZE = "Medium & large"
"""

# ---- YOUR SETTINGS (edit these) -------------------------------------------
AGE_CUTOFF = 70        # count owners this age or older
SECTOR = None          # e.g. "Manufacturing", "Construction", "Agriculture" - or None for all
REGION = None          # e.g. "Wales", "London", "South West" - or None for all
SIZE = None            # "Micro", "Small" or "Medium & large" - or None for all
# ---------------------------------------------------------------------------

import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from succession.analyse import universes  # noqa: E402

df = pd.read_pickle(os.path.join(HERE, "data", "processed", "companies.pkl"))
_, om, op = universes(df)
d = om if SECTOR == "Real estate" else op
filters = []
for col, val in (("sector", SECTOR), ("region", REGION), ("size", SIZE)):
    if val is not None:
        if val not in set(d[col].astype(str)):
            sys.exit(f'"{val}" is not a valid {col}. Options: {sorted(set(d[col].astype(str)))}')
        d = d[d[col] == val]
        filters.append(f"{col} = {val}")

age = d["lead_owner_age"]
old = d[age >= AGE_CUTOFF]
name = ", ".join(filters) or "all owner-managed operating businesses"
lines = [
    f"QUESTION: {name}, owners aged {AGE_CUTOFF}+",
    "-" * 60,
    f"Businesses in this group:          {len(d):>10,}",
    f"With a lead owner aged {AGE_CUTOFF}+:        {len(old):>10,}",
    f"Share:                             {len(old) / max(len(d), 1):>10.1%}",
    f"Median owner age:                  {age.median():>10.0f}",
    f"Of those {AGE_CUTOFF}+, with no secured debt:  {(old['charges_outstanding'] == 0).mean():>9.1%}",
    "",
]
by = "region" if REGION is None else "sector"
if SECTOR is not None and REGION is None:
    by = "region"
g = d.groupby(by, observed=True)["lead_owner_age"]
t = pd.DataFrame({"businesses": g.size(), f"owner_{AGE_CUTOFF}_plus": g.apply(lambda s: int((s >= AGE_CUTOFF).sum()))})
t["share"] = t[f"owner_{AGE_CUTOFF}_plus"] / t["businesses"]
t = t[(t["businesses"] >= 100) & ~t.index.astype(str).isin(["Unknown", "Other / overseas"])].sort_values("share", ascending=False)
lines.append(f"BREAKDOWN BY {by.upper()} (groups with 100+ businesses):")
for k, r in t.iterrows():
    lines.append(f"  {str(k):<28}{r['share']:>7.1%}   ({int(r[f'owner_{AGE_CUTOFF}_plus']):,} of {int(r['businesses']):,})")

text = "\n".join(lines)
print("\n" + text + "\n")
os.makedirs(os.path.join(HERE, "output", "my_analysis"), exist_ok=True)
fname = f"age{AGE_CUTOFF}" + "".join(f"_{v}" for v in (SECTOR, REGION, SIZE) if v)
path = os.path.join(HERE, "output", "my_analysis", fname.replace(" ", "-").replace("&", "and") + ".txt")
with open(path, "w") as f:
    f.write(text + "\n")
print(f"Saved to: {path}")
