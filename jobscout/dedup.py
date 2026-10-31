"""Never send the same job twice, and never send a job the user already applied to.

state/seen.tsv     every posting already sent, one per line: key, date, company, title, url
state/applied.csv  applications: date, company, title, url, status. Edit it by hand or with
                   `python -m jobscout applied add URL`.
"""
import csv
import re
from datetime import date
from pathlib import Path

APPLIED_FIELDS = ["date", "company", "title", "url", "status"]


def url_key(url):
    """A stable id for a job across URL variants: Ashby/Lever UUID, Greenhouse id, Workday requisition."""
    u = (url or "").strip().rstrip(".,)")
    for rx in (r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", r"gh_jid=(\d+)",
               r"[?&]token=(\d{5,})", r"/jobs/(\d{5,})", r"_((?:R|JR|REQ)?[A-Z0-9-]*\d{4,}(?:-\d+)?)(?:[/?#]|$)"):
        m = re.search(rx, u, re.I)
        if m:
            return m.group(1).lower()
    return u.lower()


_ABBREV = [(r"\bsr\.?\b", "senior"), (r"\bpm\b", "product manager"), (r"\bdir\.?\b", "director"),
           (r"\bvp\b", "vice president"), (r"\bmgr\b", "manager"), (r"[^a-z0-9 ]", " ")]


def norm(s):
    s = (s or "").lower()
    for a, b in _ABBREV:
        s = re.sub(a, b, s)
    return " ".join(s.split())


def role_key(company, title):
    return f"{norm(company)}|{norm(title)}"


class Ledger:
    def __init__(self, state_dir):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_path = self.dir / "seen.tsv"
        self.applied_path = self.dir / "applied.csv"
        self.seen_urls, self.seen_roles = {}, set()
        if self.seen_path.exists():
            for line in self.seen_path.read_text(encoding="utf-8").splitlines():
                f = line.split("\t")
                if len(f) >= 5:
                    self.seen_urls[f[0]] = f[1]
                    self.seen_roles.add(role_key(f[2], f[3]))
        self.applied = self.read_applied()
        self.applied_urls = {url_key(a["url"]): a for a in self.applied if a.get("url")}
        self.applied_roles = {role_key(a["company"], a["title"]): a for a in self.applied}

    def read_applied(self):
        if not self.applied_path.exists():
            return []
        with self.applied_path.open(encoding="utf-8", newline="") as f:
            return [r for r in csv.DictReader(f) if r.get("company") or r.get("url")]

    def status(self, p):
        """NEW, SEEN or APPLIED for a Posting."""
        k = url_key(p.url)
        rk = role_key(p.company, p.title)
        if k in self.applied_urls or rk in self.applied_roles:
            return "APPLIED"
        if k in self.seen_urls or rk in self.seen_roles:
            return "SEEN"
        return "NEW"

    def record_sent(self, postings):
        today = date.today().isoformat()
        with self.seen_path.open("a", encoding="utf-8") as f:
            for p in postings:
                clean = [x.replace("\t", " ").replace("\n", " ") for x in (p.company, p.title, p.url)]
                f.write("\t".join([url_key(p.url), today, *clean]) + "\n")

    def add_applied(self, company, title, url="", status="applied", when=None):
        new = not self.applied_path.exists()
        with self.applied_path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=APPLIED_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"date": when or date.today().isoformat(), "company": company, "title": title,
                        "url": url, "status": status})
