"""Cheap, rule-based filters that run before any paid call."""
import re
from datetime import date, timedelta


def _rx(terms):
    terms = [t for t in terms if t]
    return re.compile("|".join(f"(?:{t})" for t in terms), re.I) if terms else None


class Filter:
    def __init__(self, search):
        self.inc = _rx(search["title_include"])
        self.exc = _rx(search["title_exclude"])
        self.loc_inc = _rx(search["location_include"])
        self.loc_exc = _rx(search["location_exclude"])
        self.remote_ok = search["remote_ok"]
        self.cutoff = (date.today() - timedelta(days=search["max_age_days"])).isoformat()

    def title_ok(self, title):
        return bool((not self.inc or self.inc.search(title)) and not (self.exc and self.exc.search(title)))

    def location_ok(self, location, remote=False):
        if self.loc_exc and self.loc_exc.search(location or ""):
            return False
        if not self.loc_inc:
            return True
        if self.remote_ok and (remote or re.search(r"\bremote\b", location or "", re.I)):
            return True
        return bool(self.loc_inc.search(location or ""))

    def fresh(self, posted):
        """Unknown dates pass: dropping them would hide whole boards that omit dates."""
        return not posted or posted >= self.cutoff

    def why_not(self, p):
        if not self.title_ok(p.title):
            return "title"
        if not self.fresh(p.posted):
            return "age"
        if not self.location_ok(p.location, p.remote):
            return "location"
        return None
