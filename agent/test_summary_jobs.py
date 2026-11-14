"""Offline tests for the three scoring fixes: wrong-company sites, honest job sources, buyer-first summary.
Run from the agent folder:  python3 -m unittest test_summary_jobs -v   (needs only requests + beautifulsoup4)."""
import unittest

import core
import web

TS = "2026-11-14T03:37:54Z"


class SummaryLead(unittest.TestCase):
    def test_revenue_first_with_source(self):
        s = core.build_summary("1", {"official_legal_name": "ACME AS", "financial_revenue": "NOK 5 000 (FY ending 2025-12-31)"},
                               {"period_end": "2025-12-31"}, TS)
        self.assertTrue(s.startswith("ACME AS reported revenue of NOK 5 000 for the period ending 2025-12-31 (Brønnøysund Regnskapsregisteret"))

    def test_job_lead_names_the_real_host(self):
        job = {"title": "Deltidsekspeditør", "url": "https://www.jobbnorge.no/x/1", "posted_at": "2026-11-12",
               "origin": "job_board_name_match"}
        s = core.build_summary("1", {"official_legal_name": "ACME AS"}, None, TS, [job])
        self.assertIn("on Jobbnorge", s)
        self.assertNotIn("own site", s)
        self.assertIn("posted 2026-11-12", s)

    def test_company_site_job_may_say_own_careers_page(self):
        job = {"title": "Industrimekanikar", "url": "https://acme.no/jobb/1", "posted_at": None, "origin": "company_site"}
        s = core.build_summary("1", {"official_legal_name": "ACME AS"}, None, TS, [job])
        self.assertIn("listed on its own careers page", s)

    def test_dated_job_beats_undated(self):
        a = {"title": "Undated role", "url": "https://acme.no/a", "posted_at": None, "origin": "company_site"}
        b = {"title": "Dated role", "url": "https://jobbnorge.no/b", "posted_at": "2026-11-01", "origin": "job_board_name_match"}
        self.assertEqual(core.best_job([a, b])["title"], "Dated role")

    def test_no_registry_field_leads_when_news_exists(self):
        f = {"official_legal_name": "ACME AS", "industry": "94.992 Aktiviteter", "employees": 5,
             "news": [{"title": "Ny kontrakt med kommunen", "url": "https://acme.no/n/1", "published_at": "2026-10-01"}]}
        s = core.build_summary("1", f, None, TS)
        self.assertTrue(s.startswith("ACME AS published a dated news post on 2026-10-01"))
        self.assertNotIn("operates in", s)

    def test_employees_then_manager_then_industry(self):
        self.assertIn("registered employees", core.build_summary("1", {"official_legal_name": "A AS", "employees": 28, "industry": "x"}, None, TS))
        s = core.build_summary("1", {"official_legal_name": "A AS", "general_manager": "Ola Nordmann", "industry": "x"}, None, TS)
        self.assertIn("led by general manager Ola Nordmann", s)
        self.assertIn("is chaired by Kari Nordmann", core.build_summary("1", {"official_legal_name": "A AS", "chair": "Kari Nordmann", "industry": "x"}, None, TS))
        self.assertTrue(core.build_summary("1", {"official_legal_name": "A AS", "industry": "94.992 X"}, None, TS).startswith("A AS operates in"))

    def test_no_boilerplate_claim(self):
        s = core.build_summary("1", {"official_legal_name": "A AS", "employees": 3}, None, TS)
        self.assertNotIn("Every claim has its own source URL", s)


class JobFilters(unittest.TestCase):
    def test_call_to_action_titles_are_not_postings(self):
        for t in ("Sjekk ledige stillinger", "See open positions", "Browse all jobs", "Finn din drømmejobb hos oss i dag"):
            self.assertFalse(web.valid_job_title(t), t)
        for t in ("Søker salgskonsulent", "Prosjektleder bygg", "Deltidsekspeditør"):
            self.assertTrue(web.valid_job_title(t), t)

    def test_group_card_must_name_this_exact_employer(self):
        self.assertFalse(web.employer_matches_label("Telenor Norge", "TELENOR ASA"))
        self.assertFalse(web.employer_matches_label("", "TELENOR ASA"))
        self.assertTrue(web.employer_matches_label("Telenor", "TELENOR ASA"))

    def test_origin_labels(self):
        self.assertEqual(web.job_origin("Jobbnorge public job API, employer matched by exact employer name"), "job_board_name_match")
        self.assertEqual(web.job_origin("Jobbnorge public job API, employer matched by the employer link on the company site"), "linked_from_company_site")
        self.assertEqual(web.job_origin("link on the company's careers page"), "company_site")


class WrongCompanySites(unittest.TestCase):
    def test_sister_and_group_domains_rejected(self):
        self.assertFalse(web.domain_matches_name("rekonstrukt.no", "TREEMBALLASJE AS"))
        self.assertFalse(web.domain_matches_name("obos.no", "SAMEIET EGNERKVARTALET"))
        self.assertFalse(web.domain_matches_name("ww.obos.no", "SAMEIET EGNERKVARTALET"))
        self.assertTrue(web.domain_matches_name("obos.no", "OBOS BBL"))


if __name__ == "__main__":
    unittest.main()
