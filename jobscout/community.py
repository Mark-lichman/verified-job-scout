"""Optional community job boards. Off by default: turn one on only if its terms allow it.

Mind the Product (mindtheproduct.com/jobs) publishes a JSON list of product jobs, each with
the employer's own apply link. Those links still go through the live check.
"""
from datetime import datetime, timedelta, timezone

from .ats import Posting, parse_url
from .http import get_json


def mindtheproduct(days, country="US", max_pages=40):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for page in range(1, max_pages + 1):
        st, d = get_json(f"https://www.mindtheproduct.com/api/jobs/list/?country={country}&page={page}&pageSize=50")
        if not d:
            break
        stop = False
        for j in d.get("jobs", []):
            try:
                t = datetime.fromisoformat(str(j.get("publishedAt")).replace("Z", "+00:00"))
            except ValueError:
                t = None
            if t and t < cutoff:
                stop = True
                continue
            url = j.get("applicationUrl") or ""
            ats, board, jid = parse_url(url)
            out.append(Posting(ats, board, jid, j.get("title") or "", j.get("company") or "",
                               j.get("location") or "?", url, posted=(j.get("publishedAt") or "")[:10],
                               remote="remote" in (j.get("location") or "").lower(), source="community"))
        if stop or not d.get("hasMore"):
            break
    return out
