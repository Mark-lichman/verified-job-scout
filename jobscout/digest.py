"""Render the shortlist as Markdown (for files and GitHub) and HTML (for email)."""
import html
from datetime import date

from .score import tier


def _groups(postings, sc):
    groups = {"A": [], "B": [], "C": [], "Unscored": []}
    for p in postings:
        groups[tier(p.extra.get("score"), sc)].append(p)
    return groups


LABELS = {"A": "Tier A: apply today", "B": "Tier B: worth a look", "C": "Tier C: also seen",
          "Unscored": "Verified matches (unscored)"}


def markdown(postings, stats, sc):
    today = date.today().isoformat()
    lines = [f"# Job shortlist, {today}", "",
             f"{len(postings)} roles. Every link was open on the employer's own job board when this ran.", ""]
    n = 0
    for t, items in _groups(postings, sc).items():
        if not items:
            continue
        lines += [f"## {LABELS[t]}", ""]
        for p in items:
            n += 1
            score = p.extra.get("score")
            lines.append(f"### {n}. {p.title} at {p.company}" + (f" ({score}/100)" if score is not None else ""))
            lines.append(f"- **Where:** {p.location}{' (remote)' if p.remote and 'remote' not in p.location.lower() else ''}")
            lines.append(f"- **Pay:** {p.extra.get('comp_label', 'not stated')}"
                         + (" (bottom of range is under your floor)" if p.extra.get("comp") == "STRADDLES" else ""))
            if p.posted:
                lines.append(f"- **Posted:** {p.posted}")
            for k, label in (("why", "Why you"), ("concern", "Concern"), ("lead_with", "Lead with")):
                if p.extra.get(k):
                    lines.append(f"- **{label}:** {p.extra[k]}")
            lines += [f"- **Apply:** {p.url}", ""]
    lines += ["---", "", "**This run:** " + ", ".join(f"{k} {v}" for k, v in stats.items()), ""]
    return "\n".join(lines)


def to_html(md):
    """Small Markdown-to-HTML pass for the shapes markdown() emits. No dependency needed."""
    import re
    out = []
    for line in md.splitlines():
        esc = html.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        esc = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', esc)
        if line.startswith("### "):
            out.append(f"<h3 style='margin:18px 0 4px'>{esc[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2 style='margin:24px 0 8px;border-bottom:1px solid #ddd'>{esc[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1 style='font-size:22px'>{esc[2:]}</h1>")
        elif line.startswith("- "):
            out.append(f"<div style='margin:2px 0 2px 12px'>{esc[2:]}</div>")
        elif line == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{esc}</p>")
    return ("<div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.45;"
            "max-width:680px;color:#111'>" + "\n".join(out) + "</div>")
