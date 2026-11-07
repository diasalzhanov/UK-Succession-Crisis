"""Headline numbers, tables and charts."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SOURCE = "Source: Companies House bulk data (company register + PSC register), {snap}. Analysis: Dias."

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def universes(df):
    trading = df[df["trading"] & (df["company_age"] >= 2)]
    om = trading[(trading["owner_type"] == "Owner-managed") & trading["lead_owner_age"].notna()]
    operating = om[om["sector"] != "Real estate"]
    return trading, om, operating


def share_table(d, by, min_n=500):
    g = d.groupby(by, observed=True)["lead_owner_age"]
    t = pd.DataFrame({
        "businesses": g.size(),
        "owner_65_plus": g.apply(lambda s: int((s >= 65).sum())),
        "owner_70_plus": g.apply(lambda s: int((s >= 70).sum())),
        "median_owner_age": g.median(),
    })
    t["pct_65_plus"] = t["owner_65_plus"] / t["businesses"]
    t["pct_70_plus"] = t["owner_70_plus"] / t["businesses"]
    return t[t["businesses"] >= min_n].sort_values("pct_65_plus", ascending=False)


def _finish(fig, ax, title, subtitle, snap, path):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5, color=INK2)
    fig.text(0.01, 0.01, SOURCE.format(snap=snap), fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _hbar(t, title, subtitle, snap, path, overall):
    t = t.sort_values("pct_65_plus")
    fig, ax = plt.subplots(figsize=(8, 0.38 * len(t) + 1.6))
    ax.barh(t.index.astype(str), t["pct_65_plus"] * 100, color=BLUE, height=0.65)
    for i, (p, n) in enumerate(zip(t["pct_65_plus"], t["owner_65_plus"])):
        ax.text(p * 100 + 0.3, i, f"{p:.0%}  ({n:,.0f})", va="center", fontsize=8.5, color=INK2)
    ax.axvline(overall * 100, color=INK2, lw=1, ls="--")
    ax.text(overall * 100, -0.75, f" UK average {overall:.0%}", fontsize=8.5, color=INK2, va="center")
    ax.set_ylim(-1, len(t) - 0.4)
    ax.set_xlabel("% of owner-managed businesses whose lead owner is 65+")
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(t["pct_65_plus"].max() * 100 * 1.28, overall * 100 * 1.4))
    _finish(fig, ax, title, subtitle, snap, path)


def run(df, out_dir, snap):
    charts = os.path.join(out_dir, "charts")
    tables = os.path.join(out_dir, "tables")
    os.makedirs(charts, exist_ok=True)
    os.makedirs(tables, exist_ok=True)
    trading, om, op = universes(df)
    age = op["lead_owner_age"]
    overall = float((age >= 65).mean())

    # --- tables
    by_sector = share_table(om, "sector")
    by_region = share_table(op, "region")
    by_size = share_table(op, "size", min_n=1)
    op = op.assign(company_age_band=pd.cut(op["company_age"], [0, 5, 10, 20, 30, 200],
                                           labels=["2-5", "6-10", "11-20", "21-30", "30+"], right=True))
    by_company_age = share_table(op, "company_age_band", min_n=1).sort_index()
    for name, t in [("by_sector", by_sector), ("by_region", by_region), ("by_size", by_size),
                    ("by_company_age", by_company_age)]:
        t.to_csv(os.path.join(tables, f"{name}.csv"))

    old = op[age >= 65]
    snap_year = int(snap[:4])
    young = op[age < 65]
    turn65 = (young["lead_birth_year"] + 65).astype(int).value_counts().sort_index()
    wave = turn65.loc[snap_year + 1: snap_year + 10]
    wave.rename("businesses_whose_owner_turns_65").to_csv(os.path.join(tables, "retirement_wave.csv"))

    summary = {
        "snapshot": snap,
        "active_private_ltd": int(len(df)),
        "trading_companies": int(len(trading)),
        "owner_type_share_trading": {k: round(float(v), 4) for k, v in
                                     trading["owner_type"].value_counts(normalize=True).items()},
        "owner_managed_with_age": int(len(om)),
        "operating_businesses": int(len(op)),
        "operating_owner_65_plus": int((age >= 65).sum()),
        "operating_owner_70_plus": int((age >= 70).sum()),
        "operating_owner_75_plus": int((age >= 75).sum()),
        "pct_65_plus": round(overall, 4),
        "pct_70_plus": round(float((age >= 70).mean()), 4),
        "median_owner_age": float(age.median()),
        "owner_65_plus_no_secured_debt_pct": round(float((old["charges_outstanding"] == 0).mean()), 4),
        "owner_65_plus_by_size": {k: int(v) for k, v in old["size"].value_counts().items()},
        "turning_65_next_10_years": int(wave.sum()),
        "real_estate_pct_65_plus": round(float((om.loc[om["sector"] == "Real estate", "lead_owner_age"] >= 65).mean()), 4),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # --- chart 1: age distribution
    counts = age.clip(18, 95).astype(int).value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(counts.index, counts.values, width=0.85,
           color=[ORANGE if a >= 65 else BLUE for a in counts.index])
    ax.set_xlabel("Age of lead owner")
    ax.set_ylabel("Businesses")
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="Under 65"), Patch(color=ORANGE, label=f"65+  ({summary['operating_owner_65_plus']:,})")],
              frameon=False, loc="upper left")
    _finish(fig, ax, "Who owns Britain's small businesses?",
            f"Age of the lead owner, {len(op):,} owner-managed operating companies (excl. property)",
            snap, os.path.join(charts, "1_owner_age_distribution.png"))

    # --- chart 2: retirement wave
    fig, ax = plt.subplots(figsize=(8, 4.2))
    labels = ["Already\n65+"] + [str(y) for y in wave.index]
    vals = [summary["operating_owner_65_plus"]] + list(wave.values)
    ax.bar(labels, vals, color=[ORANGE] + [BLUE] * len(wave), width=0.7)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v / 1000:,.0f}k", ha="center", va="bottom", fontsize=8.5, color=INK2)
    ax.set_ylabel("Businesses")
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    _finish(fig, ax, "The retirement wave",
            "Owner-managed businesses whose lead owner is already 65+, and the number reaching 65 each year",
            snap, os.path.join(charts, "2_retirement_wave.png"))

    # --- charts 3-4: sector & region
    _hbar(by_sector.drop(index=["Unknown"], errors="ignore"), "Which industries are most exposed?",
          "Share of owner-managed businesses with a lead owner aged 65+, by sector", snap,
          os.path.join(charts, "3_by_sector.png"),
          float((om["lead_owner_age"] >= 65).mean()))
    _hbar(by_region.drop(index=["Unknown", "Other / overseas"], errors="ignore"), "Where is the problem biggest?",
          "Share of owner-managed operating businesses with a lead owner aged 65+, by region", snap,
          os.path.join(charts, "4_by_region.png"), overall)

    # --- chart 5: company size & age
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, t, xl in [(axes[0], by_size.reindex(["Micro", "Small", "Medium & large"]).dropna(), "Company size (accounts filed)"),
                      (axes[1], by_company_age, "Company age (years)")]:
        ax.bar(t.index.astype(str), t["pct_65_plus"] * 100, color=BLUE, width=0.6)
        for i, p in enumerate(t["pct_65_plus"]):
            ax.text(i, p * 100, f"{p:.0%}", ha="center", va="bottom", fontsize=9, color=INK2)
        ax.set_xlabel(xl)
        ax.yaxis.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("% with lead owner 65+")
    fig.text(0.01, 0.95, "Exposure by company size and company age", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.01, 0.90, "Share of owner-managed operating businesses with a lead owner aged 65+",
             fontsize=9.5, color=INK2)
    fig.text(0.01, 0.01, SOURCE.format(snap=snap), fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.87))
    fig.savefig(os.path.join(charts, "5_by_size_and_company_age.png"), dpi=200)
    plt.close(fig)

    return summary, op
