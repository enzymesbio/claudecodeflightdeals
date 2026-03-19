"""
Unified money parser for all currencies seen on Google Flights.
Handles thin spaces, NBSP, decimals, and ambiguous ¥ symbol.
"""
import re
from decimal import Decimal

SPACE_RE = re.compile(r'[\u00a0\u2007\u2009\u202f]+')

# Order matters: more specific patterns first
MONEY_PATTERNS = [
    (re.compile(r'(?:US\$|USD)\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "USD"),
    (re.compile(r'HK\$\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "HKD"),
    (re.compile(r'HKD\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "HKD"),
    (re.compile(r'S\$\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "SGD"),
    (re.compile(r'SGD\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "SGD"),
    (re.compile(r'JP¥\s?(?P<amt>\d[\d,]*)', re.I), "JPY"),
    (re.compile(r'JPY\s?(?P<amt>\d[\d,]*)', re.I), "JPY"),
    (re.compile(r'KRW\s?(?P<amt>\d[\d,]*)', re.I), "KRW"),
    (re.compile(r'₩\s?(?P<amt>\d[\d,]*)', re.I), "KRW"),
    (re.compile(r'CN¥\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "CNY"),
    (re.compile(r'(?:CNY|RMB)\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "CNY"),
    (re.compile(r'MYR\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "MYR"),
    (re.compile(r'THB\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)', re.I), "THB"),
    # Plain $ last (most ambiguous — treat as USD when curr=USD in URL)
    (re.compile(r'From\s\$(?P<amt>\d[\d,]*(?:\.\d{1,2})?)'), "USD"),
    (re.compile(r'^\$(?P<amt>\d[\d,]*(?:\.\d{1,2})?)'), "USD"),
    (re.compile(r'\$(?P<amt>\d[\d,]*(?:\.\d{1,2})?)'), "USD"),
]

FX = {
    "USD": Decimal("1"),
    "HKD": Decimal("0.128"),
    "SGD": Decimal("0.75"),
    "JPY": Decimal("0.0067"),
    "KRW": Decimal("0.00075"),
    "CNY": Decimal("0.14"),
    "MYR": Decimal("0.23"),
    "THB": Decimal("0.029"),
    "PHP": Decimal("0.018"),
    "TWD": Decimal("0.031"),
}


def parse_money(text):
    """
    Parse the first money value from text. Returns dict or None.
    Result: {"currency": "USD", "amount": 514.0, "usd": 514.0}
    """
    text = SPACE_RE.sub(" ", text or "").strip()
    for rx, code in MONEY_PATTERNS:
        m = rx.search(text)
        if m:
            amt_str = m.group("amt").replace(",", "")
            try:
                amt = Decimal(amt_str)
                rate = FX.get(code, Decimal("1"))
                return {
                    "currency": code,
                    "amount": float(amt),
                    "usd": float((amt * rate).quantize(Decimal("0.01"))),
                }
            except Exception:
                continue
    return None


def parse_money_usd(text):
    """Parse text and return just the USD float value, or None."""
    result = parse_money(text)
    return result["usd"] if result else None


def parse_price_line(line):
    """
    Parse a single price line as seen on Google Flights Explore.
    Returns USD float or None.
    """
    line = SPACE_RE.sub(" ", (line or "")).strip()
    result = parse_money(line)
    if result and result["usd"] > 10:
        return result["usd"]
    return None
