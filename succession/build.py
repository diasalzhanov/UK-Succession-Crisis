"""Turn the two raw bulk files into one tidy table: one row per active UK
private limited company, with its sector, region, size and its owners' ages."""
import io
import json
import os
import re
import zipfile
from datetime import date

import pandas as pd

from .lookups import EXCLUDED_ACCOUNTS, NON_TRADING_SIC, ownership_band, region, sector, sic_code, size_group

WANT = {"CompanyNumber", "CompanyCategory", "CompanyStatus", "IncorporationDate",
        "RegAddress.PostCode", "Accounts.AccountCategory", "SICCode.SicText_1",
        "Mortgages.NumMortOutstanding"}


def _open_member(zip_path, suffixes):
    z = zipfile.ZipFile(zip_path)
    names = [n for n in z.namelist() if n.lower().endswith(suffixes)] or z.namelist()
    return z.open(names[0])


def load_companies(zip_path):
    print("    reading company list (a few minutes)...")
    parts, total = [], 0
    with _open_member(zip_path, (".csv",)) as fh:
        reader = pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                             usecols=lambda c: c.strip() in WANT, dtype=str, chunksize=250_000)
        for chunk in reader:
            chunk.columns = [c.strip() for c in chunk.columns]
            total += len(chunk)
            chunk = chunk[(chunk["CompanyStatus"].str.strip() == "Active") &
                          (chunk["CompanyCategory"].str.strip() == "Private Limited Company")]
            out = pd.DataFrame({"company_number": chunk["CompanyNumber"].str.strip()})
            sic = chunk["SICCode.SicText_1"].map(sic_code)
            out["sic"] = sic
            out["sector"] = sic.map(sector)
            out["region"] = chunk["RegAddress.PostCode"].map(region)
            acc = chunk["Accounts.AccountCategory"].fillna("").str.strip().str.upper()
            out["accounts"] = acc
            out["size"] = acc.map(size_group)
            inc = pd.to_datetime(chunk["IncorporationDate"], format="%d/%m/%Y", errors="coerce")
            out["inc_year"] = inc.dt.year
            out["charges_outstanding"] = pd.to_numeric(
                chunk["Mortgages.NumMortOutstanding"], errors="coerce").fillna(0).astype("int16")
            out["trading"] = (~acc.isin(EXCLUDED_ACCOUNTS) & (out["size"] != "Unknown")
                              & ~sic.isin(NON_TRADING_SIC) & sic.notna())
            parts.append(out)
            print(f"      {total:,} rows scanned", end="\r")
    df = pd.concat(parts, ignore_index=True)
    for c in ("sector", "region", "size", "accounts", "sic"):
        df[c] = df[c].astype("category")
    print(f"      {total:,} rows scanned -> {len(df):,} active private limited companies")
    return df


def load_owners(zip_path, universe):
    """Stream the PSC snapshot; keep a compact summary per company."""
    print("    reading owner register (5-15 minutes)...")
    agg = {}   # company -> [n_individual, has_corporate, lead_band, lead_birth_year, lead_birth_month]
    n = kept = 0
    with _open_member(zip_path, (".txt", ".json", ".jsonl")) as fh:
        for raw in io.TextIOWrapper(fh, encoding="utf-8", errors="replace"):
            n += 1
            if n % 1_000_000 == 0:
                print(f"      {n:,} records", end="\r")
            if '"ceased_on"' in raw:
                continue                        # no longer an owner
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            num = rec.get("company_number")
            if num not in universe:
                continue
            d = rec.get("data") or {}
            kind = d.get("kind", "")
            a = agg.get(num)
            if a is None:
                a = agg[num] = [0, False, -1, None, None]
            if kind.startswith("individual"):
                dob = d.get("date_of_birth") or {}
                y, m = dob.get("year"), dob.get("month", 6)
                band = ownership_band(d.get("natures_of_control"))
                a[0] += 1
                # lead owner = biggest shareholding; ties -> the older person
                if y and (band > a[2] or (band == a[2] and (a[3] is None or y < a[3]))):
                    a[2], a[3], a[4] = band, y, m
                kept += 1
            elif kind.startswith(("corporate-entity", "legal-person")):
                a[1] = True
                kept += 1
    print(f"      {n:,} records read, {kept:,} current owners matched")
    return pd.DataFrame.from_dict(
        agg, orient="index",
        columns=["n_individual_owners", "has_corporate_owner", "lead_band",
                 "lead_birth_year", "lead_birth_month"])


def snapshot_date(path):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(path))
    return date(*map(int, m.groups())) if m else date.today()


def build(paths, out_path):
    snap = snapshot_date(paths["owners"])
    comp = load_companies(paths["companies"])
    owners = load_owners(paths["owners"], set(comp["company_number"]))
    df = comp.join(owners, on="company_number")
    df["n_individual_owners"] = df["n_individual_owners"].fillna(0).astype("int16")
    df["has_corporate_owner"] = df["has_corporate_owner"].fillna(False).astype(bool)
    by, bm = df["lead_birth_year"], df["lead_birth_month"].fillna(6)
    df["lead_owner_age"] = (snap.year - by - (snap.month < bm).astype(int)).where(by.notna())
    df["owner_type"] = "No owner data"
    df.loc[df["n_individual_owners"] > 0, "owner_type"] = "Owner-managed"
    df.loc[df["has_corporate_owner"], "owner_type"] = "Corporate-owned"
    df["owner_type"] = df["owner_type"].astype("category")
    df["company_age"] = snap.year - df["inc_year"]
    df.attrs["snapshot"] = snap.isoformat()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_pickle(out_path)
    with open(out_path + ".meta.json", "w") as f:
        json.dump({"snapshot": snap.isoformat(),
                   "companies_file": os.path.basename(paths["companies"]),
                   "owners_file": os.path.basename(paths["owners"])}, f)
    print(f"    saved {len(df):,} companies -> {out_path}")
    return df
