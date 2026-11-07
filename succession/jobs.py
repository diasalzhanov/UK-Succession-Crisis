"""Estimate jobs at stake: random sample of 65+-owned businesses per size group,
read their employee counts from filed accounts, scale up with a bootstrap CI."""
import json
import os
import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .analyse import BLUE, GRID, INK, INK2, SOURCE  # noqa: E402
from .ixbrl import parse_accounts  # noqa: E402

SIZES = ["Micro", "Small", "Medium & large"]


def estimate(op, client, out_dir, snap, per_group=150, seed=42):
    old = op[op["lead_owner_age"] >= 65]
    rng = random.Random(seed)
    result = {"method": f"Simple random sample of up to {per_group} companies per size group "
                        "(seed 42); employees = average employees in latest digital accounts; "
                        "95% CI from 5,000 bootstrap resamples.", "groups": {}}
    total_mid, total_lo, total_hi = 0.0, 0.0, 0.0
    for size in SIZES:
        pool = old.loc[old["size"] == size, "company_number"].tolist()
        if not pool:
            continue
        sample = rng.sample(pool, min(per_group, len(pool)))
        emps = []
        for i, num in enumerate(sample, 1):
            e = parse_accounts(client.accounts_ixbrl(num)).get("employees")
            if e is not None and e >= 0:
                emps.append(float(e))
            if i % 25 == 0:
                print(f"      {size}: {i}/{len(sample)} sampled")
        if not emps:
            continue
        arr = np.array(emps)
        boots = np.random.default_rng(seed).choice(arr, (5000, len(arr))).mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        n_pop = len(pool)
        g = {"population": n_pop, "sampled": len(sample), "with_employee_data": len(arr),
             "mean_employees": round(float(arr.mean()), 2),
             "median_employees": float(np.median(arr)),
             "jobs_estimate": round(float(arr.mean() * n_pop)),
             "jobs_ci_low": round(float(lo * n_pop)), "jobs_ci_high": round(float(hi * n_pop))}
        result["groups"][size] = g
        total_mid += g["jobs_estimate"]
        total_lo += g["jobs_ci_low"]
        total_hi += g["jobs_ci_high"]
    result["total_jobs_estimate"] = round(total_mid)
    result["total_jobs_range_note"] = (f"Summing group CIs gives a conservative range of "
                                       f"{total_lo:,.0f} - {total_hi:,.0f}")
    result["total_ci_low"], result["total_ci_high"] = round(total_lo), round(total_hi)
    with open(os.path.join(out_dir, "jobs_estimate.json"), "w") as f:
        json.dump(result, f, indent=2)

    gs = [s for s in SIZES if s in result["groups"]]
    if gs:
        mids = [result["groups"][s]["jobs_estimate"] for s in gs]
        los = [m - result["groups"][s]["jobs_ci_low"] for s, m in zip(gs, mids)]
        his = [result["groups"][s]["jobs_ci_high"] - m for s, m in zip(gs, mids)]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(gs, mids, yerr=[los, his], color=BLUE, width=0.55, capsize=6,
               error_kw={"ecolor": INK2, "lw": 1})
        for i, m in enumerate(mids):
            ax.text(i + 0.3, m, f"~{m / 1000:,.0f}k", va="center", fontsize=9, color=INK2)
        ax.set_ylabel("Estimated employees")
        ax.yaxis.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.set_title("Jobs at stake", loc="left", fontsize=13, fontweight="bold", color=INK, pad=24)
        ax.text(0, 1.02, f"Estimated employees in businesses with a lead owner aged 65+ "
                f"(total ~{total_mid / 1e6:,.2f}m; bars show 95% CI)",
                transform=ax.transAxes, fontsize=9.5, color=INK2)
        fig.text(0.01, 0.01, SOURCE.format(snap=snap) + "\nEmployee counts from a random sample of filed digital accounts.",
                 fontsize=7.5, color=INK2)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        fig.savefig(os.path.join(out_dir, "charts", "6_jobs_at_stake.png"), dpi=200)
        plt.close(fig)
    return result
