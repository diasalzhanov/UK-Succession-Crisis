"""Companies House API client with disk cache, rate limiting and retries."""
import hashlib
import json
import os
import time

import requests

API = "https://api.company-information.service.gov.uk"


class CompaniesHouse:
    def __init__(self, api_key, cache_dir, cache_days=7, min_interval=0.55):
        self.session = requests.Session()
        self.session.auth = (api_key, "")
        self.session.headers["User-Agent"] = "succession-research/1.0"
        self.cache_dir = cache_dir
        self.cache_secs = cache_days * 86400
        self.min_interval = min_interval
        self._last = 0.0
        self.calls = 0
        os.makedirs(cache_dir, exist_ok=True)

    # ---------------------------------------------------------------- internals
    def _cache_path(self, key, ext):
        h = hashlib.sha1(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.{ext}")

    def _cached(self, path):
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < self.cache_secs:
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None

    def _request(self, url, params=None, headers=None):
        for attempt in range(6):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=30)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429:
                print("    rate limit hit - pausing 60s...")
                time.sleep(60)
                continue
            if r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 401:
                raise SystemExit("Companies House rejected the API key (401). "
                                 "Check api_key.txt - it should be a REST API key.")
            return r
        return None

    def get_json(self, path_or_url, params=None):
        url = path_or_url if path_or_url.startswith("http") else API + path_or_url
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        cpath = self._cache_path(key, "json")
        hit = self._cached(cpath)
        if hit is not None:
            return json.loads(hit)
        r = self._request(url, params=params)
        if r is None or r.status_code == 404:
            data = {}
        elif r.status_code != 200:
            return {}
        else:
            data = r.json()
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    # ------------------------------------------------------------------ endpoints
    def advanced_search(self, sic_code, incorporated_to, location="", size=100):
        params = {
            "sic_codes": sic_code,
            "company_status": "active",
            "company_type": "ltd",
            "incorporated_to": incorporated_to,
            "size": min(int(size), 5000),
        }
        if location:
            params["location"] = location
        return self.get_json("/advanced-search/companies", params).get("items", [])

    def profile(self, number):
        return self.get_json(f"/company/{number}")

    def officers(self, number):
        return self.get_json(f"/company/{number}/officers",
                             {"items_per_page": 100}).get("items", [])

    def pscs(self, number):
        return self.get_json(f"/company/{number}/persons-with-significant-control",
                             {"items_per_page": 100}).get("items", [])

    def charges(self, number):
        return self.get_json(f"/company/{number}/charges").get("items", [])

    def accounts_filings(self, number):
        return self.get_json(f"/company/{number}/filing-history",
                             {"category": "accounts", "items_per_page": 5}).get("items", [])

    def accounts_ixbrl(self, number):
        """Return the latest digitally-filed accounts (iXBRL html) or None."""
        for filing in self.accounts_filings(number):
            meta_url = (filing.get("links") or {}).get("document_metadata")
            if not meta_url:
                continue
            cpath = self._cache_path("doc:" + meta_url, "html")
            hit = self._cached(cpath)
            if hit is not None:
                return hit or None
            meta = self.get_json(meta_url)
            if "application/xhtml+xml" not in (meta.get("resources") or {}):
                # paper/PDF-only filing - can't be read automatically; try older one
                continue
            r = self._request(meta_url.rstrip("/") + "/content",
                              headers={"Accept": "application/xhtml+xml"})
            html = r.text if r is not None and r.status_code == 200 else ""
            with open(cpath, "w", encoding="utf-8") as f:
                f.write(html)
            return html or None
        return None
