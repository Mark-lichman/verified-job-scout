"""Offline tests: no network. Run with: python -m unittest"""
import tempfile
import unittest

from jobscout import comp
from jobscout.ats import Posting, parse_url, strip_html, _workday_age
from jobscout.config import DEFAULTS
from jobscout.dedup import Ledger, norm, url_key
from jobscout.filters import Filter


def posting(**kw):
    base = dict(ats="greenhouse", board="acme", job_id="123", title="Senior Product Manager",
                company="Acme", location="San Francisco, CA", url="https://job-boards.greenhouse.io/acme/jobs/1234567")
    base.update(kw)
    return Posting(**base)


class ParseUrl(unittest.TestCase):
    def test_boards(self):
        self.assertEqual(parse_url("https://job-boards.greenhouse.io/abridge/jobs/4451765009"),
                         ("greenhouse", "abridge", "4451765009"))
        self.assertEqual(parse_url("https://job-boards.greenhouse.io/embed/job_app?for=myome&token=4451765009"),
                         ("greenhouse", "myome", "4451765009"))
        self.assertEqual(parse_url("https://jobs.ashbyhq.com/Hippocratic%20AI/0b2f-uuid"),
                         ("ashby", "Hippocratic%20AI", "0b2f-uuid"))
        self.assertEqual(parse_url("https://jobs.lever.co/zapsurgical/abc-123/apply")[:2], ("lever", "zapsurgical"))
        ats, board, jid = parse_url("https://gh.wd1.myworkdayjobs.com/en-US/gh/job/Palo-Alto/Senior-PM_R123")
        self.assertEqual((ats, board, jid), ("workday", "gh.wd1.myworkdayjobs.com gh", "/job/Palo-Alto/Senior-PM_R123"))

    def test_aggregator_and_unknown(self):
        self.assertEqual(parse_url("https://builtin.com/job/pm/123")[0], "aggregator")
        self.assertEqual(parse_url("https://www.linkedin.com/jobs/view/1")[0], "aggregator")
        self.assertEqual(parse_url("https://careers.example.com/jobs/1")[0], "unknown")


class Comp(unittest.TestCase):
    def test_text_ranges(self):
        p = posting(description="... The base pay range for this role is $165,000 - $205,000 per year.")
        self.assertEqual(comp.check(p, 175000), ("STRADDLES", "$165K-$205K"))
        self.assertEqual(comp.check(p, 210000)[0], "BELOW_FLOOR")
        self.assertEqual(comp.check(p, 0)[0], "OK")

    def test_k_and_hourly(self):
        self.assertEqual(comp.ranges("Pay: $180k to $220k"), [(180000.0, 220000.0)])
        self.assertEqual(comp.ranges("$45 - $60 per hour"), [])

    def test_structured(self):
        self.assertEqual(comp.ranges("{'minValue': 182000, 'maxValue': 240000}"), [(182000.0, 240000.0)])
        self.assertEqual(comp.check(posting(), 175000)[0], "NOT_STATED")


class Dedup(unittest.TestCase):
    def test_url_key(self):
        self.assertEqual(url_key("https://job-boards.greenhouse.io/acme/jobs/4451765009?gh_src=x"), "4451765009")
        self.assertEqual(url_key("https://acme.com/careers?gh_jid=4451765009"), "4451765009")
        self.assertEqual(url_key("https://jobs.ashbyhq.com/Unlearn/0B2F1C3D-1111-2222-3333-444455556666"),
                         url_key("https://jobs.ashbyhq.com/unlearn/0b2f1c3d-1111-2222-3333-444455556666/application"))

    def test_norm(self):
        self.assertEqual(norm("Sr. PM, Platform"), norm("Senior Product Manager Platform"))

    def test_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            led = Ledger(d)
            p = posting()
            self.assertEqual(led.status(p), "NEW")
            led.record_sent([p])
            self.assertEqual(Ledger(d).status(p), "SEEN")
            led.add_applied("Beta", "Sr. PM")
            self.assertEqual(Ledger(d).status(posting(company="Beta", url="https://x/y")), "APPLIED")


class Filters(unittest.TestCase):
    def test_rules(self):
        s = dict(DEFAULTS["search"], location_include=["San Francisco", "Bay Area"])
        f = Filter(s)
        self.assertIsNone(f.why_not(posting()))
        self.assertEqual(f.why_not(posting(title="Product Marketing Manager")), "title")
        self.assertEqual(f.why_not(posting(location="Austin, TX")), "location")
        self.assertIsNone(f.why_not(posting(location="Remote, US")))
        self.assertEqual(f.why_not(posting(posted="2001-01-01")), "age")
        self.assertIsNone(f.why_not(posting(posted="")))


class Misc(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(strip_html("&lt;p&gt;Hi&lt;/p&gt;<b>there</b>"), "Hi\n there")

    def test_workday_age(self):
        self.assertTrue(_workday_age("Posted Today"))
        self.assertEqual(_workday_age("Posted on a date"), "")


if __name__ == "__main__":
    unittest.main()
