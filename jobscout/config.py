"""Load config.toml and the board lists. Every setting has a default, so a near-empty config runs."""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "profile": "profile.md",
    "state_dir": "state",
    "digest_dir": "digests",
    "search": {
        # Product management roles by default. Change these two lists for any other job family.
        "title_include": [r"product (manager|management|lead|leader|director|officer)",
                          r"\b(head|director|vp|vice president|chief|svp|evp)\b.*\bproduct",
                          r"\b(group|principal|staff|senior|lead) product\b", r"\bcpo\b"],
        "title_exclude": ["marketing", "designer", "analyst", "engineer", "intern", "associate product",
                          "junior", r"\bapm\b", "counsel", "support", "specialist", "reviewer", "sales",
                          "contract(or)?\\b"],
        "workday_terms": ["product manager", "director product", "head of product",
                          "vice president product", "principal product", "senior product manager"],
        "location_include": [],     # regexes; empty means any location
        "remote_ok": True,
        "location_exclude": [],
        "max_age_days": 14,
    },
    "boards": {"lists": ["health"], "extra": []},
    "pay": {"floor": 0},
    "discovery": {"enabled": True, "queries": [], "num_results": 10, "find_companies": []},
    "community": {"mindtheproduct": False},
    "scoring": {"model": "claude-haiku-5-5", "max_candidates": 40, "max_results": 15,
                "tier_a": 70, "tier_b": 55, "batch_size": 8},
    "notify": {"method": "file", "to": "", "from": "", "smtp_host": "smtp.gmail.com", "smtp_port": 587,
               "subject": "Job shortlist for {date}: {count} roles"},
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path=None):
    path = Path(path or os.environ.get("JOBSCOUT_CONFIG") or ROOT / "config.toml")
    user = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = _merge(DEFAULTS, user)
    cfg["_root"] = str(path.parent if path.exists() else ROOT)
    return cfg


def resolve(cfg, rel):
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["_root"]) / p


def read_profile(cfg):
    p = resolve(cfg, cfg["profile"])
    return p.read_text(encoding="utf-8") if p.exists() else ""


def read_boards(cfg):
    """Boards from boards/<list>.txt, the config's extra list and the boards discovery found.
    Returns a sorted list of (ats, board)."""
    boards = set()
    files = [ROOT / "boards" / f"{name}.txt" for name in cfg["boards"]["lists"]]
    files.append(resolve(cfg, cfg["state_dir"]) / "boards-discovered.txt")
    lines = []
    for f in files:
        if f.exists():
            lines += f.read_text(encoding="utf-8").splitlines()
    lines += cfg["boards"]["extra"]
    for line in lines:
        line = line.split("#")[0].strip()
        if not line:
            continue
        ats, *rest = line.split()
        if rest:
            boards.add((ats.lower(), " ".join(rest)))
    return sorted(boards)
