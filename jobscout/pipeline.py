"""One run: find boards, sweep them, filter, dedupe, check pay, score, send.

The core guarantee: every posting in the shortlist came from a call to the employer's own job
board API during this run, so it was open when the shortlist was built. Search results and
community boards only ever add BOARDS to sweep, never postings to report.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from . import comp, community, config, digest, notify
from .ats import SUPPORTED, fetch_detail, list_board
from .dedup import Ledger
from .discover import discover
from .filters import Filter
from .score import Scorer


def run(cfg, dry_run=False, log=print):
    stats = Counter()
    state = config.resolve(cfg, cfg["state_dir"])
    ledger = Ledger(state)
    flt = Filter(cfg["search"])
    boards = set(config.read_boards(cfg))
    log(f"boards: {len(boards)} in your lists")

    # 1. Discovery adds boards, never postings.
    new_boards, _, exa = discover(cfg, boards, log)
    if cfg["community"]["mindtheproduct"]:
        mtp = community.mindtheproduct(cfg["search"]["max_age_days"])
        found = {(p.ats, p.board) for p in mtp if p.ats in SUPPORTED and p.board and flt.title_ok(p.title)}
        log(f"community: Mind the Product had {len(mtp)} recent jobs on {len(found)} supported boards")
        new_boards |= {b for b in found if b not in boards}
    boards |= new_boards
    stats["boards"] = len(boards)

    # 2. Sweep every board through its own API.
    terms = cfg["search"]["workday_terms"]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda b: (b, list_board(b[0], b[1], terms)), sorted(boards)))
    postings, silent = [], 0
    for b, jobs in results:
        silent += not jobs
        postings += jobs
    stats["open jobs"] = len(postings)
    log(f"sweep: {len(postings)} open jobs on {len(boards) - silent} boards ({silent} empty or not answering)")

    # 3. Rules: title, age, location. Then never repeat a job or show one already applied to.
    kept, drops = [], Counter()
    seen_keys = set()
    for p in postings:
        reason = flt.why_not(p)
        if not reason:
            st = ledger.status(p)
            reason = None if st == "NEW" else st.lower()
        if not reason and p.key in seen_keys:
            reason = "duplicate"
        if reason:
            drops[reason] += 1
            continue
        seen_keys.add(p.key)
        kept.append(p)
    log("filter: kept %d; dropped %s" % (len(kept), dict(drops)))
    stats["matched"] = len(kept)

    cap = cfg["scoring"]["max_candidates"]
    if len(kept) > cap:
        kept.sort(key=lambda p: p.posted or "", reverse=True)
        log(f"filter: {len(kept)} matches is over max_candidates ({cap}); keeping the {cap} newest")
        kept = kept[:cap]

    # 4. Full posting text, then the pay gate (pay ranges sit at the end of a posting).
    with ThreadPoolExecutor(max_workers=8) as pool:
        kept = list(pool.map(fetch_detail, kept))
    floor = cfg["pay"]["floor"]
    survivors = []
    for p in kept:
        verdict, label = comp.check(p, floor)
        p.extra.update(comp=verdict, comp_label=label)
        if verdict == "BELOW_FLOOR":
            stats["below pay floor"] += 1
        else:
            survivors.append(p)

    # 5. Score with Claude, keep the best.
    scorer = Scorer(cfg, config.read_profile(cfg))
    ranked = scorer.score(survivors, log)
    stats["dropped by profile rules"] = len(survivors) - len(ranked)
    final = ranked[: cfg["scoring"]["max_results"]]
    stats["sent"] = len(final)
    if scorer.tokens_in:
        stats["Claude tokens"] = f"{scorer.tokens_in} in / {scorer.tokens_out} out"
    if exa.calls:
        stats["Exa cost"] = f"${exa.cost:.3f}"

    # 6. Write, send, remember.
    md = digest.markdown(final, dict(stats), cfg["scoring"])
    out_dir = config.resolve(cfg, cfg["digest_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    (out_dir / f"{today}.md").write_text(md, encoding="utf-8")
    html_body = digest.to_html(md)
    (out_dir / f"{today}.html").write_text(html_body, encoding="utf-8")
    log(f"digest: {len(final)} roles written to {out_dir / (today + '.md')}")
    if dry_run:
        log("dry run: nothing sent, nothing recorded")
        return final
    subject = cfg["notify"]["subject"].format(date=today, count=len(final))
    if final and notify.send(cfg, subject, md, html_body, log):
        log(f"notify: sent by {cfg['notify']['method']}")
    ledger.record_sent(final)
    if new_boards:
        with (Path(state) / "boards-discovered.txt").open("a", encoding="utf-8") as f:
            f.writelines(f"{a} {b}  # found {today}\n" for a, b in sorted(new_boards))
    return final
