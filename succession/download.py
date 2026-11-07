"""Download the two free Companies House bulk files (skips them if already here)."""
import os
import re
import sys
import time

import requests

BASE = "https://download.companieshouse.gov.uk/"
PRODUCTS = {
    "companies": ("en_output.html", r'href="(BasicCompanyDataAsOneFile-\d{4}-\d{2}-\d{2}\.zip)"'),
    "owners": ("en_pscdata.html", r'href="(persons-with-significant-control-snapshot-\d{4}-\d{2}-\d{2}\.zip)"'),
}


def _latest_name(page, pattern):
    html = requests.get(BASE + page, timeout=60).text
    names = sorted(set(re.findall(pattern, html)))
    if not names:
        raise SystemExit(f"Couldn't find the download link on {BASE + page} - "
                         "Companies House may have changed the page.")
    return names[-1]


def _fetch(name, dest_dir):
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
        print(f"    already downloaded: {name}")
        return dest
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(BASE + name, stream=True, timeout=120, headers=headers) as r:
        if have and r.status_code != 206:      # server ignored resume - start again
            have = 0
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) + have
        done, t0, last = have, time.time(), 0
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 2:
                    last = time.time()
                    mb = done / 1e6
                    pct = f"{100 * done / total:.0f}%" if total else ""
                    speed = (done - have) / 1e6 / max(time.time() - t0, 1)
                    sys.stdout.write(f"\r    {name}: {mb:,.0f} MB {pct}  ({speed:.1f} MB/s)   ")
                    sys.stdout.flush()
    os.replace(part, dest)
    print(f"\r    downloaded: {name}{' ' * 30}")
    return dest


def download_all(raw_dir):
    os.makedirs(raw_dir, exist_ok=True)
    paths = {}
    for key, (page, pattern) in PRODUCTS.items():
        name = _latest_name(page, pattern)
        paths[key] = _fetch(name, raw_dir)
    return paths


def find_local(raw_dir):
    """Newest already-downloaded files, or None if missing."""
    out = {}
    for key, (_, pattern) in PRODUCTS.items():
        rx = re.compile(pattern.split('"')[1])
        files = sorted(f for f in os.listdir(raw_dir) if rx.fullmatch(f)) if os.path.isdir(raw_dir) else []
        out[key] = os.path.join(raw_dir, files[-1]) if files else None
    return out
