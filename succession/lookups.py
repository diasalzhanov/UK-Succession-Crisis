"""Lookup tables: SIC division -> sector, postcode area -> region, accounts -> size."""
import re

# UK SIC 2007 sections, keyed by 2-digit division ranges
_SECTIONS = [
    (1, 3, "A", "Agriculture"), (5, 9, "B", "Mining & quarrying"), (10, 33, "C", "Manufacturing"),
    (35, 35, "D", "Energy"), (36, 39, "E", "Water & waste"), (41, 43, "F", "Construction"),
    (45, 47, "G", "Wholesale & retail"), (49, 53, "H", "Transport & storage"),
    (55, 56, "I", "Hospitality"), (58, 63, "J", "Info & communication"),
    (64, 66, "K", "Finance & insurance"), (68, 68, "L", "Real estate"),
    (69, 75, "M", "Professional & technical"), (77, 82, "N", "Admin & support"),
    (84, 84, "O", "Public admin"), (85, 85, "P", "Education"), (86, 88, "Q", "Health & social care"),
    (90, 93, "R", "Arts & recreation"), (94, 96, "S", "Other services"),
    (97, 98, "T", "Households"), (99, 99, "U", "Extraterritorial"),
]
NON_TRADING_SIC = {"99999", "74990", "98000"}   # dormant / non-trading / residents' property mgmt


def sic_code(text):
    m = re.match(r"\s*(\d{4,5})", str(text or ""))
    return m.group(1).zfill(5) if m else None


def sector(code):
    if not isinstance(code, str) or not code:
        return "Unknown"
    div = int(code[:2])
    for lo, hi, _, name in _SECTIONS:
        if lo <= div <= hi:
            return name
    return "Unknown"


# Postcode AREA (the letters at the start) -> ONS region. Area level is approximate
# for a few border areas (e.g. SY, CH, TD, EN) - documented as a limitation.
_REGIONS = {
    "North East": "DH DL NE SR TS",
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN",
    "Yorkshire & Humber": "BD DN HD HG HU HX LS S WF YO",
    "East Midlands": "DE LE LN NG NN",
    "West Midlands": "B CV DY HR ST TF WR WS WV",
    "East of England": "AL CB CM CO EN IP LU NR PE SG SS WD",
    "London": "E EC N NW SE SW W WC BR CR HA IG RM SM TW UB",
    "South East": "BN CT DA GU HP KT ME MK OX PO RG RH SL SO TN",
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR",
    "Wales": "CF LD LL NP SA SY",
    "Scotland": "AB DD DG EH FK G HS IV KA KW KY ML PA PH TD ZE",
    "Northern Ireland": "BT",
}
AREA_TO_REGION = {a: r for r, s in _REGIONS.items() for a in s.split()}


def region(postcode):
    m = re.match(r"\s*([A-Za-z]{1,2})\d", str(postcode or ""))
    if not m:
        return "Unknown"
    return AREA_TO_REGION.get(m.group(1).upper(), "Other / overseas")


# Accounts category (Basic Company Data, upper case) -> size group
_SIZE = {
    "MICRO ENTITY": "Micro",
    "TOTAL EXEMPTION FULL": "Small", "TOTAL EXEMPTION SMALL": "Small",
    "UNAUDITED ABRIDGED": "Small", "AUDITED ABRIDGED": "Small", "SMALL": "Small",
    "PARTIAL EXEMPTION": "Small",
    "MEDIUM": "Medium & large", "FULL": "Medium & large", "GROUP": "Medium & large",
}
EXCLUDED_ACCOUNTS = {"DORMANT", "NO ACCOUNTS FILED", "AUDIT EXEMPTION SUBSIDIARY",
                     "FILING EXEMPTION SUBSIDIARY", "INITIAL"}


def size_group(cat):
    return _SIZE.get(str(cat or "").strip().upper(), "Unknown")


_BAND = re.compile(r"ownership-of-shares-(\d+)-to")


def ownership_band(natures):
    """Highest share band held (75, 50, 25), or 0 for control without shares."""
    best = 0
    for n in natures or []:
        m = _BAND.search(n)
        if m:
            best = max(best, int(m.group(1)))
    return best
