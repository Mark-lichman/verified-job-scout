"""Read the pay range from a posting and compare it with the user's floor.

Pay-transparency ranges usually sit at the END of a posting, so this reads the whole body plus
the board's structured pay fields. A truncated read reports 'not stated' for roles that state a range.
"""
import re

NUM = r"(\d{2,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d+)?\s?[kK]|\d{5,6}(?:\.\d+)?)"
RANGE = re.compile(r"\$\s?" + NUM + r"\s*(?:USD|usd)?\s*(?:-|–|—|to|and)\s*(?:USD\s*)?\$?\s?" + NUM)
MIN_ANNUAL = 60000  # anything lower is an hourly rate or a bonus line


def _money(s):
    s = s.replace(",", "").strip()
    return float(s[:-1]) * 1000 if s[-1] in "kK" else float(s)


def ranges(text):
    out = []
    for m in RANGE.finditer(text or ""):
        lo, hi = sorted((_money(m.group(1)), _money(m.group(2))))
        if hi >= MIN_ANNUAL:
            out.append((lo, hi))
    for lo, hi in re.findall(r"['\"]minValue['\"]:\s*(\d+(?:\.\d+)?),\s*['\"]maxValue['\"]:\s*(\d+(?:\.\d+)?)", text or ""):
        if float(hi) >= MIN_ANNUAL:
            out.append((float(lo), float(hi)))
    for lo, hi in re.findall(r"['\"]min_cents['\"]:\s*(\d+),\s*['\"]max_cents['\"]:\s*(\d+)", text or ""):
        if int(hi) / 100 >= MIN_ANNUAL:
            out.append((int(lo) / 100, int(hi) / 100))
    return out


def check(p, floor):
    """Returns (verdict, label). verdict: OK, STRADDLES, BELOW_FLOOR or NOT_STATED."""
    rs = ranges(f"{p.comp_text} {p.description}")
    if not rs:
        return "NOT_STATED", "not stated"
    lo, hi = min(r[0] for r in rs), max(r[1] for r in rs)
    label = f"${lo / 1000:.0f}K-${hi / 1000:.0f}K"
    if not floor:
        return "OK", label
    if hi < floor:
        return "BELOW_FLOOR", label
    return ("STRADDLES" if lo < floor else "OK"), label
