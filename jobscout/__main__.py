"""Command line: python -m jobscout <command>"""
import argparse
import sys

from . import config, pipeline
from .ats import list_board, parse_url, verify
from .dedup import Ledger


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="jobscout", description="A daily job shortlist where every link is verified live.")
    ap.add_argument("--config", help="path to config.toml (default: ./config.toml or $JOBSCOUT_CONFIG)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="build today's shortlist and send it")
    r.add_argument("--dry-run", action="store_true", help="write the digest file only: no email, no state changes")

    v = sub.add_parser("verify", help="check whether posting links are open right now")
    v.add_argument("urls", nargs="+")

    a = sub.add_parser("applied", help="record or list applications, so they never come back")
    asub = a.add_subparsers(dest="action", required=True)
    add = asub.add_parser("add")
    add.add_argument("url", nargs="?", default="")
    add.add_argument("--company", default="")
    add.add_argument("--title", default="")
    add.add_argument("--status", default="applied")
    asub.add_parser("list")

    b = sub.add_parser("board", help="list the open jobs on one board, e.g. 'board greenhouse abridge'")
    b.add_argument("ats")
    b.add_argument("board", nargs="+")

    args = ap.parse_args(argv)
    cfg = config.load(args.config)

    if args.cmd == "run":
        pipeline.run(cfg, dry_run=args.dry_run)
    elif args.cmd == "verify":
        bad = 0
        for u in args.urls:
            verdict, detail = verify(u)
            bad += verdict != "LIVE"
            print(f"{verdict:<10} {u} :: {detail}")
        return 1 if bad else 0
    elif args.cmd == "applied":
        ledger = Ledger(config.resolve(cfg, cfg["state_dir"]))
        if args.action == "list":
            for row in ledger.applied:
                print(" | ".join(row.get(k, "") for k in ("date", "company", "title", "status", "url")))
            return 0
        company, title = args.company, args.title
        if args.url and not (company and title):
            ats, board, jid = parse_url(args.url)
            for p in list_board(ats, board) if ats != "workday" else []:
                if p.job_id.lower() == jid.lower():
                    company, title = company or p.company, title or p.title
        if not (company and title):
            print("Could not read the company and title from that link. Pass --company and --title.")
            return 1
        ledger.add_applied(company, title, args.url, args.status)
        print(f"recorded: {company} | {title}")
    elif args.cmd == "board":
        cfg_terms = cfg["search"]["workday_terms"]
        for p in list_board(args.ats, " ".join(args.board), cfg_terms):
            print(f"{p.posted or '?':<10} | {p.title} | {p.location} | {p.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
