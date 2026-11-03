# verified-job-scout

A daily shortlist of jobs that fit you, where **every link is open on the employer's own job board** when you get it.

Job boards and search engines keep showing roles that closed weeks ago. In one early test of the tool this grew from, 8 of 15 links in a "fresh" shortlist were already dead. Greenhouse and Ashby even answer a closed job's page with a normal-looking page, so you only find out after you start the application.

This tool skips all that. It reads open jobs straight from each employer's applicant tracking system (the ATS: Greenhouse, Ashby, Lever, Workable and Workday), filters them by your rules, drops anything you already saw or applied to, checks the pay range against your floor, and has Claude score what is left against your profile. Then it emails you the short list.

It never applies for you and never contacts an employer.

## How it works

```
your board lists ──┐
Exa search ────────┼─> boards ─> sweep each board's API ─> title, age and location rules
community boards ──┘                (live by definition)            │
                                                                     v
          email <─ shortlist <─ Claude scores fit <─ pay floor <─ already seen or applied?
```

1. **Boards.** It starts from board lists in `boards/` (the starter list has about 640 health and health-tech employers, each checked live on 2026-11-02), plus your own. Optional [Exa](https://exa.ai) searches find boards your lists miss and save them for later runs.
2. **Sweep.** It asks each board's public API for its open jobs. A job the API lists is open right now. That is the "verified" in the name: **search results only ever add boards to sweep, never postings to report.**
3. **Rules.** Title, posting age and location filters run for free before any paid step.
4. **Memory.** It never repeats a job it already sent, or one in your applied list.
5. **Pay.** It reads the whole posting, because pay ranges usually sit at the very end, and drops roles whose entire range is below your floor.
6. **Fit.** One small Claude call per batch scores fit against your `profile.md`, with a one-line reason, a concern and what to lead with.
7. **Delivery.** It saves the shortlist to `digests/` and can email it by SMTP (for example Gmail) or [Resend](https://resend.com).

## Quick start

You need Python 3.11 or newer. There are no packages to install.

```bash
git clone https://github.com/Mark-lichman/verified-job-scout
cd verified-job-scout
cp config.example.toml config.toml     # your rules
cp profile.example.md profile.md       # who you are, in plain words
python -m jobscout run --dry-run       # builds the shortlist in digests/ and sends nothing
```

The first run with no API keys still works: you get every verified match, listed by date without scores. Add keys to turn on the paid steps:

| Key | What it adds | Rough cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | Fit scores and reasons from Claude | A few cents per run with the default Haiku model |
| `EXA_API_KEY` | Finds new boards through search | Under $0.01 per search. Exa's free tier covers light use. |
| `SMTP_PASSWORD` or `RESEND_API_KEY` | Email delivery | Free |

Set them as environment variables, then run `python -m jobscout run`.

## Run it on GitHub Actions (free, no computer needed)

1. Create your own copy of this repository. A **private** copy is safest.
2. In your copy, open **Settings, Secrets and variables, Actions** and add:
   - `JOBSCOUT_PROFILE`: the full text of your `profile.md`
   - `JOBSCOUT_CONFIG`: the full text of your `config.toml`
   - `ANTHROPIC_API_KEY`, `EXA_API_KEY` (optional)
   - For Gmail: `SMTP_USER` (your address) and `SMTP_PASSWORD` (a Google [app password](https://myaccount.google.com/apppasswords)), with `method = "smtp"` in your config
3. Open the **Actions** tab, choose **daily shortlist** and click **Run workflow** to test it.

It then runs every morning. Your profile and settings stay in secrets, never in the code, and the record of sent jobs persists between runs in the Actions cache.

## Everyday commands

```bash
python -m jobscout run                         # build and send today's shortlist
python -m jobscout applied add <posting-url>   # you applied: never show this role again
python -m jobscout applied list
python -m jobscout verify <url> [<url> ...]    # is this posting still open?
python -m jobscout board greenhouse abridge    # list one board's open jobs
```

`state/applied.csv` is a plain spreadsheet file: date, company, title, url, status. You can also edit it by hand.

## Adding boards

Each line in a board list is `<ats> <board>`:

```
greenhouse abridge
ashby ramp
lever kariusdx
workable some-company
workday abbott.wd5.myworkdayjobs.com AbbottCareers
```

The board name is the part of the employer's jobs URL right after the ATS domain, for example `jobs.ashbyhq.com/ramp`. Add your own under `[boards] extra` in `config.toml`, or add a new file in `boards/` and name it in `[boards] lists`. Pull requests with new board lists for other industries are welcome.

## Privacy and fair use

- Your profile, settings, applied list and shortlists are ignored by git (see `.gitignore`), so they never reach a public repository by accident.
- The tool only calls public job board APIs that employers publish for job seekers, at a gentle rate. It does not scrape LinkedIn, log in anywhere or apply on your behalf.
- Posting text is treated as untrusted data in the scoring prompt, so instructions hidden in a job post are ignored.

## Limits

- Only the five ATS systems above are supported. Employers on iCIMS, Taleo, SuccessFactors, Jobvite and others are not swept yet.
- Workday has no "list all jobs" call, so it is searched with the terms in `workday_terms`.
- Scores are only as good as your profile. Write it plainly, with facts.

## License

MIT. See [LICENSE](LICENSE).
