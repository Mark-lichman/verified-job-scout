"""Employer job boards (ATS = applicant tracking system): list open jobs, fetch one job, verify a link.

Everything here talks to the employer's own public board API. Those answers are authoritative:
a job the API lists is open right now. Search engines and aggregators are not: they keep
closed postings indexed for weeks, and Greenhouse and Ashby answer a dead job page with
HTTP 200 and a board index, so a status code proves nothing.
"""
import html
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .http import get_json, post_json, request

SUPPORTED = ("greenhouse", "ashby", "lever", "workable", "workday")

# Job sites that repost other employers' jobs. Never report one of these as the apply link.
AGGREGATORS = re.compile(
    r"(^|\.)(builtin|virtualvocations|ziprecruiter|glassdoor|indeed|jobgether|remoterocketship|"
    r"theladders|zippia|swooped|jobleads|dynamitejobs|linkedin|simplyhired|talent|jooble|adzuna)\.",
    re.I,
)


@dataclass
class Posting:
    ats: str
    board: str            # greenhouse slug, ashby org, workday "host site"
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: str = ""      # YYYY-MM-DD, best available date from the API
    remote: bool = False
    description: str = ""  # plain text; filled by fetch_detail()
    comp_text: str = ""    # structured pay fields as text; filled by fetch_detail()
    source: str = "sweep"  # sweep | discovery | community
    verified: str = ""     # LIVE / DEAD / ... once checked
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.ats}:{self.board.lower()}:{self.job_id.lower()}"


def strip_html(t):
    t = html.unescape(t or "")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def _date(v):
    """Normalize ISO strings and epoch milliseconds to YYYY-MM-DD."""
    if not v:
        return ""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, timezone.utc).strftime("%Y-%m-%d")
    return str(v)[:10]


def _pretty(slug):
    return urllib.parse.unquote(slug).replace("-", " ").replace("_", " ").strip().title()


# ---------------------------------------------------------------- URL parsing

def parse_url(url):
    """Identify the board behind a posting URL. Returns (ats, board, job_id) or (kind, host, '')
    where kind is 'aggregator' or 'unknown'."""
    u = urllib.parse.urlparse(url.strip())
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    q = urllib.parse.parse_qs(u.query)
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return "ashby", parts[0], parts[1]
    if host in ("job-boards.greenhouse.io", "boards.greenhouse.io"):
        if "embed" in parts and q.get("for") and q.get("token"):
            return "greenhouse", q["for"][0], q["token"][0]
        m = re.search(r"/jobs/(\d+)", u.path)
        if parts and m:
            return "greenhouse", parts[0], m.group(1)
    if "gh_jid" in q:  # employer career page wrapping a Greenhouse job
        return "greenhouse", "", q["gh_jid"][0]
    if host == "jobs.lever.co" and len(parts) >= 2:
        return "lever", parts[0], parts[1]
    if host == "apply.workable.com" and len(parts) >= 3 and parts[1] == "j":
        return "workable", parts[0], parts[2]
    if host.endswith(".myworkdayjobs.com"):
        if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
            parts = parts[1:]
        if len(parts) >= 2 and "job" in parts:
            return "workday", f"{host} {parts[0]}", "/" + "/".join(parts[1:])
    if AGGREGATORS.search(host):
        return "aggregator", host, ""
    return "unknown", host, ""


# ---------------------------------------------------------------- listing a board

def list_board(ats, board, title_terms=()):
    """All open jobs on one board, as Posting objects. Returns [] if the board does not answer."""
    fn = {"greenhouse": _list_greenhouse, "ashby": _list_ashby, "lever": _list_lever,
          "workable": _list_workable, "workday": _list_workday}.get(ats)
    if not fn:
        return []
    try:
        return fn(board, title_terms) if ats == "workday" else fn(board)
    except Exception:
        return []


def _list_greenhouse(slug):
    st, d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not d:
        return []
    out = []
    for j in d.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or "?"
        out.append(Posting("greenhouse", slug, str(j.get("id")), j.get("title", ""),
                           j.get("company_name") or _pretty(slug), loc, j.get("absolute_url") or "",
                           posted=_date(j.get("first_published") or j.get("updated_at")),
                           remote="remote" in loc.lower()))
    return out


def _list_ashby(org):
    st, d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true")
    if not d:
        return []
    out = []
    for j in d.get("jobs", []):
        if j.get("isListed") is False:
            continue
        url = j.get("jobUrl") or ""
        jid = url.rstrip("/").split("/")[-1] if url else str(j.get("id"))
        loc = j.get("location") or "?"
        comp = j.get("compensation") or {}
        out.append(Posting("ashby", org, jid, j.get("title", ""), _pretty(org), loc, url,
                           posted=_date(j.get("publishedAt")),
                           remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
                           description=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
                           comp_text=(comp.get("compensationTierSummary") or "") + " " + str(comp)))
    return out


def _list_lever(slug):
    st, d = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(d, list):  # a bad slug answers with an error object, not a list
        return []
    out = []
    for j in d:
        cats = j.get("categories") or {}
        loc = cats.get("location") or "?"
        sr = j.get("salaryRange") or {}
        comp = f"${sr.get('min')} - ${sr.get('max')} {sr.get('interval', '')}" if sr.get("min") else ""
        lists = " ".join((l.get("text") or "") + " " + strip_html(l.get("content")) for l in j.get("lists") or [])
        desc = " ".join([j.get("descriptionPlain") or strip_html(j.get("description")), lists,
                         j.get("additionalPlain") or strip_html(j.get("additional")),
                         j.get("salaryDescriptionPlain") or ""])
        out.append(Posting("lever", slug, j.get("id", ""), j.get("text", ""), _pretty(slug), loc,
                           j.get("hostedUrl") or "", posted=_date(j.get("createdAt")),
                           remote=j.get("workplaceType") == "remote" or "remote" in loc.lower(),
                           description=desc, comp_text=comp))
    return out


def _list_workable(slug):
    st, d = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if not d:
        return []
    out = []
    for j in d.get("jobs") or []:
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x) or "?"
        url = j.get("url") or j.get("shortlink") or ""
        out.append(Posting("workable", slug, j.get("shortcode", ""), j.get("title", ""),
                           d.get("name") or _pretty(slug), loc, url, posted=_date(j.get("published_on")),
                           remote=bool(j.get("telecommuting")),
                           description=strip_html(j.get("description"))))
    return out


def _list_workday(board, title_terms=()):
    """Workday has no 'list everything' call, so search the board once per title term."""
    host, site = board.split()
    tenant = host.split(".")[0]
    seen, out = set(), []
    for term in title_terms or ("product",):
        st, d = post_json(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                          {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term})
        for j in (d or {}).get("jobPostings", []):
            path = j.get("externalPath") or ""
            if not path or path in seen:
                continue
            seen.add(path)
            loc = j.get("locationsText") or "?"
            out.append(Posting("workday", board, path, j.get("title", ""), _pretty(tenant), loc,
                               f"https://{host}/{site}{path}", posted=_workday_age(j.get("postedOn")),
                               remote="remote" in loc.lower()))
    return out


def _workday_age(text):
    """Workday lists say 'Posted Today', 'Posted Yesterday', 'Posted 5 Days Ago', 'Posted 30+ Days Ago'."""
    from datetime import timedelta
    t = (text or "").lower()
    today = datetime.now(timezone.utc).date()
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    else:
        m = re.search(r"(\d+)\+?\s*day", t)
        if not m:
            return ""
        days = int(m.group(1)) + (1 if "+" in t else 0)
    return (today - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- one job

def fetch_detail(p):
    """Fill description and comp_text for postings whose list call does not include them.
    Pay ranges usually sit at the END of a posting, so the whole body is kept."""
    try:
        if p.ats == "greenhouse" and not p.description:
            st, d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{p.board}/jobs/{p.job_id}?pay_transparency=true")
            if d:
                p.description = strip_html(d.get("content"))
                p.comp_text = str(d.get("pay_input_ranges") or "")
        elif p.ats == "workday" and not p.description:
            host, site = p.board.split()
            st, d = get_json(f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}{p.job_id}")
            info = (d or {}).get("jobPostingInfo") or {}
            p.description = strip_html(info.get("jobDescription"))
            p.posted = info.get("startDate") or p.posted
            p.remote = p.remote or info.get("remoteType") == "Remote"
    except Exception:
        pass
    return p


def verify(url):
    """Is this posting open right now? Returns (verdict, detail).
    verdict is LIVE, DEAD, AGGREGATOR or UNKNOWN. Only LIVE may reach a digest."""
    ats, board, jid = parse_url(url)
    try:
        if ats == "aggregator":
            return "AGGREGATOR", f"{board} reposts other employers' jobs; find the employer's own posting"
        if ats == "greenhouse" and board:
            r = request(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}")
            if r.status == 200:
                d = r.json() or {}
                return "LIVE", f"{d.get('title', '?')} | {(d.get('location') or {}).get('name', '?')}"
            return ("DEAD", "greenhouse api 404") if r.status == 404 else ("UNKNOWN", f"greenhouse http {r.status}")
        if ats in ("ashby", "lever", "workable"):
            jobs = list_board(ats, board)
            if not jobs:
                return "UNKNOWN", f"{ats} board '{board}' did not answer"
            for j in jobs:
                if j.job_id.lower() == jid.lower() or jid.lower() in j.url.lower():
                    return "LIVE", f"{j.title} | {j.location}"
            return "DEAD", f"not on the live {ats} board ({len(jobs)} open roles)"
        if ats == "workday":
            host, site = board.split()
            r = request(f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}{jid}")
            if r.status == 200:
                info = (r.json() or {}).get("jobPostingInfo") or {}
                if info:
                    return "LIVE", f"{info.get('title', '?')} | {info.get('location', '?')}"
                return "DEAD", "workday returned no jobPostingInfo"
            return ("DEAD", "workday api 404") if r.status == 404 else ("UNKNOWN", f"workday http {r.status}")
    except Exception as e:
        return "UNKNOWN", f"verifier error: {e}"
    return "UNKNOWN", f"no authoritative API for {board or url}"


# ---------------------------------------------------------------- finding a company's board

_ATS_LINK = re.compile(
    r"([A-Za-z0-9_.-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[A-Za-z0-9_-]+)|"
    r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)|"
    r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)|"
    r"jobs\.lever\.co/([A-Za-z0-9_-]+)|"
    r"apply\.workable\.com/([A-Za-z0-9_-]+)"
)
_NOT_SLUGS = {"embed", "api", "v1", "jobs", "j"}


def find_boards(domain):
    """Scan a company's careers pages for links to a supported job board.
    Returns a set of (ats, board) tuples."""
    domain = re.sub(r"^https?://", "", domain).split("/")[0]
    stem = domain[4:] if domain.startswith("www.") else domain
    found = set()
    for base in (f"https://{stem}", f"https://www.{stem}", f"https://careers.{stem}", f"https://jobs.{stem}"):
        for path in ("/careers", "/jobs", "", "/company/careers", "/about/careers"):
            r = request(base + path, headers={"Accept": "text/html"}, timeout=10)
            if r.status != 200:
                continue
            for m in _ATS_LINK.finditer(r.text):
                wd, gh, ash, lev, wk = m.groups()
                if wd:
                    host, *rest = wd.split("/")
                    rest = [x for x in rest if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", x)]
                    if rest:
                        found.add(("workday", f"{host.lower()} {rest[0]}"))
                elif gh and gh.lower() not in _NOT_SLUGS:
                    found.add(("greenhouse", gh))
                elif ash and ash.lower() not in _NOT_SLUGS:
                    found.add(("ashby", ash))
                elif lev and lev.lower() not in _NOT_SLUGS:
                    found.add(("lever", lev))
                elif wk and wk.lower() not in _NOT_SLUGS:
                    found.add(("workable", wk))
            if found:
                return found
    return found
