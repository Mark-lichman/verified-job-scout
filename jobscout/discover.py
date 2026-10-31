"""Find job boards the starter lists do not cover, using Exa search (https://exa.ai).

Two routes, both cheap:
1. Search the job-board domains directly ("director of product healthcare" on Greenhouse,
   Ashby, Lever). A result proves a board exists. Its posting may already be closed, so the
   posting is verified like any other, and the BOARD is saved so every later run sweeps it.
2. Search for companies ("seed-stage healthtech startups"), then scan each company's
   careers page for its board.

Discovered boards go to state/boards-discovered.txt. Search results are never reported as
postings without a live check on the employer's own board.
"""
import os
from datetime import date, timedelta

from .ats import find_boards, parse_url
from .http import post_json

EXA_URL = "https://api.exa.ai/search"
BOARD_DOMAINS = ["jobs.ashbyhq.com", "job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co",
                 "apply.workable.com"]


class Exa:
    def __init__(self, key=None):
        self.key = key or os.environ.get("EXA_API_KEY", "")
        self.cost = 0.0
        self.calls = 0

    def search(self, query, num=10, days=None, include_domains=None, category=None):
        if not self.key:
            return []
        body = {"query": query, "numResults": num, "type": "auto"}
        if days:
            body["startPublishedDate"] = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00.000Z"
        if include_domains:
            body["includeDomains"] = include_domains
        if category:
            body["category"] = category
        st, d = post_json(EXA_URL, body, headers={"x-api-key": self.key}, timeout=40)
        self.calls += 1
        if not d:
            return []
        self.cost += float((d.get("costDollars") or {}).get("total") or 0)
        return d.get("results") or []


def discover(cfg, known_boards, log=print):
    """Returns (new_boards, posting_urls). new_boards is a set of (ats, board)."""
    dc = cfg["discovery"]
    exa = Exa()
    if not dc["enabled"] or not exa.key:
        if dc["enabled"]:
            log("discovery: skipped (no EXA_API_KEY)")
        return set(), [], exa
    known = {(a, b.lower()) for a, b in known_boards}
    new, urls = set(), []
    days = cfg["search"]["max_age_days"]
    for q in dc["queries"]:
        for r in exa.search(q, num=dc["num_results"], days=days, include_domains=BOARD_DOMAINS):
            ats, board, jid = parse_url(r.get("url", ""))
            if ats in ("greenhouse", "ashby", "lever", "workable") and board:
                urls.append(r["url"])
                if (ats, board.lower()) not in known:
                    new.add((ats, board))
    for q in dc["find_companies"]:
        for r in exa.search(q, num=dc["num_results"], category="company"):
            for ats, board in find_boards(r.get("url", "")):
                if (ats, board.lower()) not in known:
                    new.add((ats, board))
    log(f"discovery: {exa.calls} Exa searches, {len(new)} new boards, {len(urls)} posting links, ${exa.cost:.3f}")
    return new, urls, exa
