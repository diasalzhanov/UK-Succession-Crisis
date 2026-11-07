"""Pull headline numbers out of iXBRL (digitally filed) UK company accounts."""
from html.parser import HTMLParser

# our field -> XBRL concept local-names to look for (first match wins)
CONCEPTS = {
    "turnover": ["TurnoverRevenue", "Turnover", "Revenue"],
    "operating_profit": ["OperatingProfitLoss"],
    "profit_before_tax": ["ProfitLossOnOrdinaryActivitiesBeforeTax", "ProfitLossBeforeTax"],
    "profit": ["ProfitLoss", "ProfitLossForPeriod"],
    "depreciation": ["DepreciationExpensePropertyPlantEquipment",
                     "IncreaseFromDepreciationChargeForYearPropertyPlantEquipment",
                     "DepreciationAmortisationImpairmentExpense",
                     "DepreciationAmortisationExpense"],
    "net_assets": ["NetAssetsLiabilities", "NetAssetsLiabilitiesIncludingPensionAssetLiability",
                   "Equity"],
    "cash": ["CashBankOnHand", "CashBankInHand", "CashCashEquivalents",
             "CashCashEquivalentsCashFlowValue"],
    "interest_payable": ["InterestPayableSimilarChargesFinanceCosts"],
    "employees": ["AverageNumberEmployeesDuringPeriod", "EmployeesTotal"],
}


def _local(name):
    return name.split(":")[-1] if name else ""


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}          # id -> {"date": str, "segment": bool}
        self.facts = []             # dicts: concept, context, text, scale, sign, format
        self._ctx = None
        self._date_tag = None
        self._fact = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        t = _local(tag)
        if t == "context":
            self._ctx = a.get("id")
            self.contexts[self._ctx] = {"date": "", "segment": False}
        elif self._ctx and t in ("enddate", "instant"):
            self._date_tag = t
        elif self._ctx and t in ("segment", "scenario"):
            self.contexts[self._ctx]["segment"] = True
        elif t == "nonfraction" and self._fact is None:
            self._fact = {"concept": _local(a.get("name", "")), "context": a.get("contextref"),
                          "scale": a.get("scale", "0"), "sign": a.get("sign", ""),
                          "format": a.get("format", ""), "text": ""}
            self._depth = 1
        elif self._fact is not None:
            self._depth += 1

    def handle_endtag(self, tag):
        t = _local(tag)
        if t == "context":
            self._ctx = None
        elif t in ("enddate", "instant"):
            self._date_tag = None
        if self._fact is not None:
            self._depth -= 1
            if self._depth <= 0 or t == "nonfraction":
                self.facts.append(self._fact)
                self._fact = None

    def handle_data(self, data):
        if self._ctx and self._date_tag:
            self.contexts[self._ctx]["date"] += data.strip()
        if self._fact is not None:
            self._fact["text"] += data


def _value(f):
    txt = f["text"].strip().replace(",", "").replace(" ", "").replace(" ", "")
    fmt = f["format"].lower()
    if "numcommadecimal" in fmt:
        txt = f["text"].strip().replace(".", "").replace(" ", "").replace(",", ".")
    txt = txt.strip("()£$€")
    if txt in ("", "-", "–", "—", "nil") or "zero" in fmt:
        num = 0.0
    else:
        try:
            num = float(txt)
        except ValueError:
            return None
    try:
        # some filing software tags head-counts with a bogus scale="-2", so ignore
        # scale for employee numbers
        if "Employee" not in f["concept"]:
            num *= 10 ** int(f["scale"] or 0)
    except ValueError:
        pass
    return -num if f["sign"] == "-" else num


def parse_accounts(html):
    """Return {field: value, 'period_end': date} for the most recent period."""
    if not html:
        return {}
    p = _Parser()
    try:
        p.feed(html)
    except Exception:
        return {}
    out = {}
    for field, names in CONCEPTS.items():
        for name in names:
            best = None
            for f in p.facts:
                if f["concept"] != name:
                    continue
                ctx = p.contexts.get(f["context"], {"date": "", "segment": False})
                if ctx["segment"]:
                    continue        # dimension breakdowns, not the headline figure
                val = _value(f)
                if val is None:
                    continue
                if best is None or ctx["date"] > best[0]:
                    best = (ctx["date"], val)
            if best:
                out[field] = best[1]
                out.setdefault("period_end", best[0])
                break
    # many small companies don't tag operating profit - rebuild it from
    # profit before tax + interest paid when we can
    if "operating_profit" not in out and "profit_before_tax" in out:
        out["operating_profit"] = out["profit_before_tax"] + abs(out.get("interest_payable", 0))
    return out
