"""Offline tests for website ownership, social-link and news rules (the three audit findings)."""
import unittest
from datetime import date
from unittest.mock import patch

import requests

import core
import web
from test_main import ENHET, N, full_routes, router

TODAY = date(2026, 10, 23)
NAME = "FOO NORGE AS"


class Resp:
    def __init__(self, status=200, body="", headers=None):
        self.status_code, self._body = status, body.encode("utf-8")
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"

    @property
    def text(self):
        return self._body.decode("utf-8", errors="replace")

    def iter_content(self, size):
        yield self._body

    def close(self):
        pass


def site(pages):
    """pages: {url: html | (status, body, headers) | Exception}"""
    def fake(url, **kw):
        page = pages.get(url)
        if isinstance(page, Exception):
            raise page
        if page is None:
            return Resp(404)
        if isinstance(page, str):
            return Resp(200, page)
        return Resp(*page)
    return fake


class Sess:
    def __init__(self, cap=100):
        self.budget, self.calls = core.RequestBudget(cap), 0


def dispatch(routes, web_fake):
    """core and web share the requests module, so one patched get() serves Brreg URLs and website URLs."""
    brreg = router(routes)
    return lambda url, **kw: brreg(url, **kw) if url.startswith("https://data.brreg.no") else web_fake(url, **kw)


def run(pages, website="https://foo.no", name=NAME, cap=100, number=N):
    logs = []
    with patch("web.requests.get", side_effect=site(pages)) as get, patch("web.public_host", return_value=True):
        out = web.enrich(number, name, website, Sess(cap), lambda: None, logs, TODAY)
    out["get"], out["logs"] = get, logs
    return out


FOOTER_OWN = f"<footer>Foo Norge AS · Org.nr 984 851 006 MVA</footer>"


class OwnershipTests(unittest.TestCase):
    def test_group_site_without_orgnr_or_name_is_not_verified_and_gives_nothing(self):
        home = """<html><body><h1>Foo Group</h1><a href="https://facebook.com/foogroup">fb</a>
                  <a href="/nyheter">News</a><time datetime="2026-09-01">1 sep</time><a href="/nyheter/big-group-news-item">Group wins big contract</a></body></html>"""
        r = run({"https://foo.no": home, "https://foo.no/kontakt": "<p>Foo Group ASA, 999 888 777</p>"}, website="foo.no")
        self.assertEqual(r["website"]["status"], "not_verified")
        self.assertFalse(r["website"]["verified"])
        self.assertEqual((r["social_links"], r["news"], r["items"]), ([], [], []))

    def test_verified_by_org_number_with_spaces_and_by_exact_name_on_contact_page(self):
        r = run({"https://foo.no": f"<body>{FOOTER_OWN}</body>"})
        self.assertEqual((r["website"]["status"], r["website"]["verified_by"]), ("verified", "organisation_number"))
        r = run({"https://foo.no": '<a href="/kontakt">Kontakt</a>', "https://foo.no/kontakt": "<p>Foo Norge  AS, Oslo</p>"})
        self.assertEqual(r["website"]["verified_by"], "exact_legal_name")

    def test_similar_name_or_other_org_number_does_not_verify(self):
        r = run({"https://foo.no": "<p>Foo Norge Holding AS 923 609 016</p>"})
        self.assertEqual(r["website"]["status"], "not_verified")

    def test_registry_site_of_a_parent_or_sister_company_is_never_published(self):
        # TREEMBALLASJE AS is a subsidiary in the Emineo group; rekonstrukt.no is a sister company.
        r = run({"https://rekonstrukt.no": "<body>Treemballasje AS er en del av konsernet</body>"},
                website="https://rekonstrukt.no", name="TREEMBALLASJE AS", number="981242947")
        self.assertEqual((r["website"]["status"], r["items"]), ("not_verified", []))
        # SAMEIET EGNERKVARTALET has a broken registry value (ww.obos.no) pointing at the OBOS group.
        r = run({"https://obos.no": "<body>Sameiet Egnerkvartalet</body>"},
                website="https://obos.no", name="SAMEIET EGNERKVARTALET", number="922901457")
        self.assertEqual((r["website"]["status"], r["items"]), ("not_verified", []))

    def test_domain_must_match_the_company_name(self):
        self.assertTrue(web.domain_matches_name("foo.no", "FOO NORGE AS"))
        self.assertTrue(web.domain_matches_name("www.acme-bygg.no", "ACME BYGG AS"))
        self.assertTrue(web.domain_matches_name("bjorkelangen.speiding.no", "1. BJORKELANGEN SPEIDERGRUPPE"))
        self.assertFalse(web.domain_matches_name("rekonstrukt.no", "TREEMBALLASJE AS"))
        self.assertFalse(web.domain_matches_name("obos.no", "SAMEIET EGNERKVARTALET"))
        self.assertFalse(web.domain_matches_name("emineo.no", "TREEMBALLASJE AS"))

    def test_private_hosts_are_never_fetched_and_registry_noise_is_normalised(self):
        logs = []
        with patch("web.requests.get") as get:
            out = web.enrich(N, NAME, "http://192.168.0.1/admin", Sess(), lambda: None, logs, TODAY)
        get.assert_not_called()
        self.assertEqual(out["website"]["status"], "unreachable")
        self.assertEqual(web.normalize_url("www.foo.no, foo.com"), "https://www.foo.no")
        self.assertIsNone(web.normalize_url("post@foo.no"))
        self.assertIsNone(web.normalize_url("ingen"))

    def test_redirect_to_private_address_is_refused(self):
        pages = {"https://foo.no": (301, "", {"Location": "http://127.0.0.1/x"})}
        calls = []
        def pub(host):
            calls.append(host)
            return host == "foo.no"
        logs = []
        with patch("web.requests.get", side_effect=site(pages)), patch("web.public_host", side_effect=pub):
            out = web.enrich(N, NAME, "https://foo.no", Sess(), lambda: None, logs, TODAY)
        self.assertEqual(out["website"]["status"], "unreachable")
        self.assertIn("127.0.0.1", calls)

    def test_per_company_request_limit(self):
        links = "".join(f'<a href="/kontakt{i}">Kontakt</a>' for i in range(8))
        r = run({"https://foo.no": links}, cap=100)
        self.assertLessEqual(r["get"].call_count, web.MAX_WEB_REQUESTS)
        self.assertEqual(r["website"]["status"], "not_verified")


class SocialTests(unittest.TestCase):
    def test_only_accounts_with_matching_handle_are_published(self):
        home = f"""<body>{FOOTER_OWN}
        <a href="https://www.facebook.com/foonorge">Facebook</a>
        <a href="https://www.instagram.com/foogroup/">Group IG</a>
        <a href="https://www.linkedin.com/company/foo-norge-as-1234567/">LinkedIn</a>
        <a href="https://twitter.com/themeforest">Theme</a>
        <a href="https://www.facebook.com/sharer/sharer.php?u=https://foo.no">Share</a>
        <a href="https://www.instagram.com/bysted_webbyra/">Web by Bysted</a>
        <a href="https://www.linkedin.com/in/ola-nordmann">Person</a>
        <a href="https://www.youtube.com/@fooconcern">Concern YT</a>
        </body>"""
        r = run({"https://foo.no": home})
        got = {s["platform"]: s["url"] for s in r["social_links"]}
        self.assertEqual(got, {"facebook": "https://www.facebook.com/foonorge",
                               "linkedin": "https://www.linkedin.com/company/foo-norge-as-1234567"})
        self.assertTrue(any("foogroup" in l for l in r["logs"]))

    def test_handle_may_equal_the_companys_own_verified_domain(self):
        r = run({"https://www.acme-bygg.no": '<p>Acme Bygg AS 984851006</p><a href="https://instagram.com/acmebygg">ig</a>'},
                website="www.acme-bygg.no", name="ACME BYGG AS")
        self.assertEqual([s["platform"] for s in r["social_links"]], ["instagram"])

    def test_jsonld_sameas_is_checked_the_same_way(self):
        home = FOOTER_OWN + '<script type="application/ld+json">{"@type":"Organization","sameAs":["https://facebook.com/foonorge","https://facebook.com/agency"]}</script>'
        self.assertEqual([s["url"] for s in run({"https://foo.no": home})["social_links"]], ["https://www.facebook.com/foonorge"])


ARTICLE = '<article><a href="{u}"><h3>{t}</h3></a><time datetime="{d}">{d}</time></article>'


class NewsTests(unittest.TestCase):
    def home(self, extra=""):
        return f'<body>{FOOTER_OWN}<nav><a href="/nyheter">Nyheter</a></nav>{extra}</body>'

    def test_real_dated_posts_only(self):
        listing = "<body>" \
            + ARTICLE.format(u="/nyheter/vi-har-fatt-ny-kontrakt-med-kommunen", t="Vi har fått ny kontrakt med kommunen", d="2026-09-30") \
            + ARTICLE.format(u="/nyheter/nytt-kontor-i-bergen-apner", t="Nytt kontor i Bergen åpner", d="2026-05-02") \
            + '<a href="/nyheter/arkiv">Se flere nyheter</a><time datetime="2026-10-01">1.10.2026</time>' \
            + ARTICLE.format(u="/produkter/stor-hammer-pro-2000", t="Stor hammer Pro 2000 nå på tilbud", d="2026-10-02") \
            + ARTICLE.format(u="/nyheter/framtidig-arrangement-uten-gyldig-dato", t="Arrangement i fremtiden som ikke finnes", d="2027-03-01") \
            + "</body>"
        r = run({"https://foo.no": self.home(), "https://foo.no/nyheter": listing})
        self.assertEqual([(n["published_at"], n["url"]) for n in r["news"]],
                         [("2026-09-30", "https://foo.no/nyheter/vi-har-fatt-ny-kontrakt-med-kommunen"),
                          ("2026-05-02", "https://foo.no/nyheter/nytt-kontor-i-bergen-apner")])

    def test_modified_dates_are_not_publish_dates(self):
        wp = ('<article><h2><a href="/2025/03/oppdatert-pristilbud-for-alle-kunder">Oppdatert pristilbud for alle kunder</a></h2>'
              '<time class="entry-date published" datetime="2025-03-04T09:00:00+01:00">4. mars 2025</time>'
              '<time class="updated" datetime="2026-10-20T09:00:00+01:00">20. oktober 2026</time></article>'
              '<article><h2><a href="/2026/01/kun-endret-dato-pa-denne-siden">Kun endret dato på denne siden</a></h2>'
              '<span class="modified">Sist endret <time datetime="2026-10-21">21.10.2026</time></span></article>')
        r = run({"https://foo.no": self.home(wp)})
        self.assertEqual([n["published_at"] for n in r["news"]], ["2025-03-04"])

    def test_rss_uses_pubdate_and_atom_updated_is_ignored(self):
        rss = """<rss version="2.0"><channel><lastBuildDate>Fri, 23 Oct 2026 08:00:00 GMT</lastBuildDate>
          <item><title>Vi lanserer ny nettside for kundene</title><link>https://foo.no/blogg/ny-nettside-lansert</link>
          <pubDate>Mon, 12 Oct 2026 10:00:00 +0200</pubDate></item>
          <item><title>Uten publiseringsdato men nylig endret</title><link>https://foo.no/blogg/uten-dato-her</link></item></channel></rss>"""
        atom = """<feed xmlns="http://www.w3.org/2005/Atom"><updated>2026-10-23T00:00:00Z</updated>
          <entry><title>Atom-innlegg som bare har updated</title><link href="https://foo.no/blogg/atom-innlegg-test"/><updated>2026-10-22T00:00:00Z</updated></entry>
          <entry><title>Atom-innlegg med published dato</title><link href="https://foo.no/blogg/atom-med-published"/><published>2026-08-01T00:00:00Z</published><updated>2026-10-22T00:00:00Z</updated></entry></feed>"""
        home = '<head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head>' + FOOTER_OWN
        r = run({"https://foo.no": home, "https://foo.no/feed.xml": (200, rss, {"Content-Type": "application/rss+xml"})})
        self.assertEqual([n["published_at"] for n in r["news"]], ["2026-10-12"])
        home = home.replace("feed.xml", "atom.xml")
        r = run({"https://foo.no": home, "https://foo.no/atom.xml": (200, atom, {"Content-Type": "application/atom+xml"})})
        self.assertEqual([n["published_at"] for n in r["news"]], ["2026-08-01"])

    def test_jsonld_uses_datepublished_never_datemodified(self):
        ld = ('<script type="application/ld+json">[{"@type":"BlogPosting","headline":"Sommerfest for alle ansatte og venner","url":"https://foo.no/blogg/sommerfest-2026",'
              '"datePublished":"2026-06-20","dateModified":"2026-10-22"},{"@type":"BlogPosting","headline":"Innlegg som mangler publiseringsdato","url":"https://foo.no/blogg/uten-publisert","dateModified":"2026-10-22"}]</script>')
        r = run({"https://foo.no": self.home(ld)})
        self.assertEqual([(n["published_at"], n["source"]) for n in r["news"]], [("2026-06-20", "JSON-LD datePublished")])

    def test_menu_labels_and_page_clock_dates_are_rejected(self):
        for label in ("See more news", "Les mer", "Flere nyheter", "Alle nyheter", "Nyheter"):
            self.assertFalse(web.valid_title(label), label)
        self.assertEqual(web.dedupe_news([{"url": f"https://foo.no/n/a{i}-x", "published_at": TODAY.isoformat()} for i in range(3)], TODAY), [])

    def test_dates_parse_norwegian_and_english(self):
        for text, want in (("12. mars 2024", date(2024, 3, 12)), ("3.11.2023", date(2023, 11, 3)), ("March 5, 2022", date(2022, 3, 5)),
                           ("2025-01-31T10:00:00Z", date(2025, 1, 31)), ("Tue, 02 Jan 2024 10:00:00 +0100", date(2024, 1, 2))):
            self.assertEqual(web.parse_date(text), want, text)
        self.assertIsNone(web.parse_date("i går"))


class RealWorldRegressionTests(unittest.TestCase):
    """Cases seen on the first real run (Equinor, DNB)."""
    def test_youtube_vanity_url_matching_the_company_is_published(self):
        home = FOOTER_OWN + '<a href="https://www.youtube.com/foonorge">YT</a><a href="https://www.youtube.com/embed/abc">v</a><a href="https://www.youtube.com/feed/x">f</a>'
        self.assertEqual([s["url"] for s in run({"https://foo.no": home})["social_links"]], ["https://www.youtube.com/foonorge"])

    def test_news_page_found_under_a_nested_path_by_link_text(self):
        home = FOOTER_OWN + '<a href="/en/about-us/news-and-media">News</a>'
        listing = ARTICLE.format(u="/en/about-us/news-and-media/new-bridge-contract-signed", t="New bridge contract signed with the county", d="2026-10-10")
        r = run({"https://foo.no": home, "https://foo.no/en/about-us/news-and-media": listing})
        self.assertEqual([n["published_at"] for n in r["news"]], ["2026-10-10"])


class SubdomainAndDomainHandleTests(unittest.TestCase):
    """Cases from the 100-company run: a scout group on a parent's subdomain, and a handle equal to the full domain."""
    def test_parent_organisations_accounts_are_not_published_for_a_subdomain_site(self):
        name = "1. BJORKELANGEN SPEIDERGRUPPE"
        home = ('<p>1. Bjorkelangen speidergruppe</p><a href="https://www.instagram.com/speiding">ig</a>'
                '<a href="https://facebook.com/speiding">fb</a><a href="https://www.facebook.com/1bjorkelangenspeidergruppe">own</a>'
                '<a href="https://www.instagram.com/bjorkelangen">own ig</a>')
        r = run({"https://bjorkelangen.speiding.no": home}, website="https://bjorkelangen.speiding.no", name=name, number=N)
        self.assertEqual(r["website"]["status"], "verified")
        self.assertEqual({s["platform"]: s["handle"] for s in r["social_links"]}, {"facebook": "1bjorkelangenspeidergruppe", "instagram": "bjorkelangen"})

    def test_handle_equal_to_full_domain_or_domain_plus_legal_suffix_matches(self):
        home = ('<p>2-CON SVERIGE AB</p><a href="https://www.instagram.com/2con.se">ig</a>'
                '<a href="https://www.linkedin.com/company/2con-ab">li</a><a href="https://www.linkedin.com/company/other-ab">no</a>')
        r = run({"https://www.2con.se": home}, website="www.2con.se", name="2-CON SVERIGE AB")
        self.assertEqual({s["platform"] for s in r["social_links"]}, {"instagram", "linkedin"})
        self.assertEqual([s for s in r["social_links"] if s["platform"] == "linkedin"][0]["handle"], "2con-ab")

    def test_own_domain_keys(self):
        self.assertEqual(set(web.own_domain_keys("bjorkelangen.speiding.no")), {"bjorkelangen"})
        self.assertEqual(set(web.own_domain_keys("foo.co.uk")), {"foo", "foocouk"})
        self.assertEqual(set(web.own_domain_keys("www.2con.se")), {"2con", "2conse"})


class JobTests(unittest.TestCase):
    def home(self, extra=""):
        return f'<body>{FOOTER_OWN}<nav><a href="/karriere">Karriere</a></nav>{extra}</body>'

    def test_postings_on_the_companys_own_careers_page(self):
        careers = ('<body><nav><a href="/om-oss">Om oss</a></nav>'
                   '<article><h3><a href="/karriere/ingenior-salg">Ingeniør salg</a></h3><time datetime="2026-10-01">1.10</time></article>'
                   '<article><h3><a href="/karriere/apen-soknad">Åpen søknad</a></h3></article>'
                   '<article><h3><a href="https://facebook.com/foonorge">Facebook</a></h3></article>'
                   '<a href="/karriere"><h3>Karriere</h3></a></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual([(j["title"], j["url"], j["posted_at"]) for j in r["jobs"]],
                         [("Ingeniør salg", "https://foo.no/karriere/ingenior-salg", "2026-10-01")])
        self.assertEqual([e["key"] for e in r["items"] if e["key"].startswith("job")], ["job_item_1"])

    def test_navigation_and_generic_pages_are_not_job_postings(self):
        careers = ('<body><nav><article><h3><a href="/om-oss/historikk">Vår historie</a></h3></article></nav>'
                   '<footer><a href="/personvern">Personvern og cookies</a></footer>'
                   '<article><h3><a href="/produkter/stor-hammer">Stor hammer Pro 2000</a></h3></article></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual(r["jobs"], [])

    def test_careers_landing_culture_and_faq_cards_are_not_postings(self):
        # Seen on obos.no/om-obos/jobb-i-obos: culture and FAQ cards under a jobs section.
        careers = ('<body><article><h3><a href="/om-obos/jobb-i-obos/en-inkluderende-kultur">Best sammen</a></h3></article>'
                   '<article><h3><a href="/om-obos/jobb-i-obos/balanse-mellom-jobb-og-fritid">Balanse mellom jobb og fritid</a></h3></article>'
                   '<article><h3><a href="/om-obos/jobb-i-obos/sporsmal-og-svar-om-rekruttering">Ofte stilte spørsmål</a></h3></article>'
                   '<article><h3><a href="/om-obos/jobb-i-obos/summer-intern-i-obos">Les mer om summer internship</a></h3></article></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual(r["jobs"], [])

    def test_listing_with_advert_links_is_a_posting(self):
        # Seen on norgesgruppen.no/karriere/ledige-stillinger/?advertId=...
        careers = ('<body><article><h3><a href="/karriere/ledige-stillinger/?advertId=123">KIWI Stokke søker butikkmedarbeider</a></h3></article>'
                   '<article><h3><a href="/karriere/ledige-stillinger/?advertId=456">MENY Nøtterøy søker avdelingsleder</a></h3></article></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual([j["title"] for j in r["jobs"]], ["KIWI Stokke søker butikkmedarbeider", "MENY Nøtterøy søker avdelingsleder"])

    def test_jsonld_jobposting_is_published_with_its_date(self):
        careers = ('<body><script type="application/ld+json">'
                   '{"@type":"JobPosting","title":"Senior prosjektleder bygg",'
                   '"url":"https://foo.no/karriere/senior-prosjektleder-bygg","datePosted":"2026-10-05"}'
                   '</script></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual([(j["title"], j["url"], j["posted_at"]) for j in r["jobs"]],
                         [("Senior prosjektleder bygg", "https://foo.no/karriere/senior-prosjektleder-bygg", "2026-10-05")])

    def test_recruitment_service_posting_linked_from_the_careers_page(self):
        careers = ('<body><article><h3><a href="https://acme.teamtailor.com/jobs/123456-senior-utvikler">Senior utvikler</a></h3></article>'
                   '<article><h3><a href="https://acme.teamtailor.com/jobs">Ledige stillinger</a></h3></article>'
                   '<article><h3><a href="https://example.recruitee.com/o/selger">Selger av byggevarer</a></h3></article></body>')
        r = run({"https://foo.no": self.home(), "https://foo.no/karriere": careers})
        self.assertEqual([j["url"] for j in r["jobs"]],
                         ["https://acme.teamtailor.com/jobs/123456-senior-utvikler",
                          "https://example.recruitee.com/o/selger"])
        self.assertTrue(all(j["found_on"] == "https://foo.no/karriere" for j in r["jobs"]))

    def test_employer_scoped_job_board_linked_from_the_site(self):
        home = (f'<body>{FOOTER_OWN}<a href="https://www.jobbnorge.no/search?employer=789#1">Ledige stillinger</a>'
                '<a href="https://www.finn.no/job/employer/company/569">Jobb hos oss</a></body>')
        board = ('<body><article><h3><a href="https://www.jobbnorge.no/ledige-stillinger/stilling/12345/butikkmedarbeider">Butikkmedarbeider</a></h3></article>'
                 '<article><h3><a href="https://www.jobbnorge.no/ledige-stillinger">Alle stillinger</a></h3></article></body>')
        r = run({"https://foo.no": home, "https://www.jobbnorge.no/search?employer=789": board})
        self.assertEqual([(j["title"], j["url"]) for j in r["jobs"]],
                         [("Butikkmedarbeider", "https://www.jobbnorge.no/ledige-stillinger/stilling/12345/butikkmedarbeider")])
        self.assertEqual(r["jobs"][0]["found_on"], "https://www.jobbnorge.no/search?employer=789")

    def test_sitemap_finds_an_unlinked_careers_page(self):
        sitemap = ('<?xml version="1.0"?><urlset><url><loc>https://foo.no/karriere/</loc></url>'
                   '<url><loc>https://foo.no/om-oss</loc></url></urlset>')
        careers = ('<body><article><h3><a href="/karriere/mekaniker">Mekaniker</a></h3></article></body>')
        r = run({"https://foo.no": f"<body>{FOOTER_OWN}</body>",
                 "https://foo.no/sitemap.xml": (200, sitemap, {"Content-Type": "application/xml"}),
                 "https://foo.no/karriere/": careers})
        self.assertEqual([j["title"] for j in r["jobs"]], ["Mekaniker"])

    def test_careers_words_alone_do_not_create_a_posting(self):
        r = run({"https://foo.no": self.home('<a href="/karriere-i-foo">Les om karriere hos oss</a>')})
        self.assertEqual(r["jobs"], [])

    def test_job_titles_reject_menu_labels(self):
        for label in ("Karriere", "Ledige stillinger", "Se alle jobber", "Åpen søknad"):
            self.assertFalse(web.valid_job_title(label), label)
        self.assertTrue(web.valid_job_title("Prosjektleder bygg"))


class SummaryTests(unittest.TestCase):
    TS = "2026-11-13T10:00:00Z"

    def test_revenue_leads_with_its_source(self):
        s = core.build_summary("984851006", {"official_legal_name": "DNB BANK ASA", "financial_revenue": "NOK 1 000 (FY ending 2025-12-31)",
                                              "company_status": "active"}, {"period_end": "2025-12-31"}, self.TS)
        self.assertTrue(s.startswith("DNB BANK ASA reported revenue of NOK 1 000 for the period ending 2025-12-31 "
                                     "(Brønnøysund Regnskapsregisteret"))

    def test_job_opening_is_the_first_fact_when_no_accounts_exist(self):
        s = core.build_summary("981242947", {"official_legal_name": "TREEMBALLASJE AS",
                                              "jobs": [{"title": "Industrimekanikar", "url": "https://example.no/jobb/1", "posted_at": None}]}, None, self.TS)
        self.assertIn("open role", s)
        self.assertIn("https://example.no/jobb/1", s)
        self.assertIn("retrieved " + self.TS, s)
        self.assertNotIn("registered as", s)          # no re-listing of registry fields


class CoreIntegrationTests(unittest.TestCase):
    def setUp(self):
        for target, value in (("BACKOFF", (0, 0)), ("MIN_INTERVAL", 0)):
            p = patch.object(core, target, value)
            p.start()
            self.addCleanup(p.stop)

    def crawl(self, pages, enrich=True):
        enhet = dict(ENHET, navn=NAME, hjemmeside="foo.no")
        routes = full_routes(**{f"{core.ENHETER}/{N}": (200, enhet)})
        with patch("requests.get", side_effect=dispatch(routes, site(pages))), patch("web.public_host", return_value=True):
            return core.crawl(N, budget=core.RequestBudget(60), enrich_web=enrich)

    def test_verified_site_adds_social_news_and_evidence(self):
        home = FOOTER_OWN + '<a href="https://facebook.com/foonorge">fb</a><a href="/nyheter">Nyheter</a>'
        listing = ARTICLE.format(u="/nyheter/vi-har-fatt-ny-kontrakt-med-kommunen", t="Vi har fått ny kontrakt med kommunen", d="2026-09-30")
        r = self.crawl({"https://foo.no": home, "https://foo.no/nyheter": listing})
        self.assertEqual(r["profile"]["website"], "https://foo.no")
        self.assertEqual(r["profile"]["social_links"], {"facebook": "https://www.facebook.com/foonorge"})
        self.assertEqual(r["profile"]["news"][0]["published_at"], "2026-09-30")
        keys = {e["target_metric_key"] for e in r["lineage_evidences"]}
        self.assertTrue({"website", "social_facebook", "news_item_1"} <= keys)
        self.assertEqual(r["website"]["verified_by"], "organisation_number")
        self.assertIn("news", r["summary"].lower())

    def test_group_site_removes_website_fact_and_explains_why(self):
        r = self.crawl({"https://foo.no": "<p>Foo Group</p>"})
        self.assertNotIn("website", r["profile"])
        self.assertIn("parent-group", r["missing_fields"]["website"])
        self.assertNotIn("social_links", r["profile"])
        self.assertEqual(r["news"], [])

    def test_unreachable_site_publishes_no_website_claim_and_is_not_a_change(self):
        store = core.SnapshotStore(None)
        home = FOOTER_OWN + '<a href="https://facebook.com/foonorge">fb</a>'
        routes = full_routes(**{f"{core.ENHETER}/{N}": (200, dict(ENHET, navn=NAME, hjemmeside="foo.no"))})
        def down(url, **kw):
            raise requests.ConnectionError("down")
        with patch("web.public_host", return_value=True):
            with patch("requests.get", side_effect=dispatch(routes, site({"https://foo.no": home}))):
                first = core.crawl(N, store=store, budget=core.RequestBudget(60))
            with patch("requests.get", side_effect=dispatch(routes, down)):
                second = core.crawl(N, store=store, budget=core.RequestBudget(60))
        self.assertEqual(second["website"]["status"], "unreachable")
        self.assertNotIn("website", second["profile"])               # unproven ownership is never asserted
        self.assertIn("could not be reached", second["missing_fields"]["website"])
        self.assertNotIn("social_links", second["profile"])
        self.assertEqual(second["update"]["status"], "unchanged")
        self.assertEqual(second["update"]["changed_fields"], [])
        self.assertIn("website", second["update"]["sources_unavailable"])

    def test_company_without_registry_website_is_reported_as_no_website(self):
        routes = full_routes(**{f"{core.ENHETER}/{N}": (200, {k: v for k, v in ENHET.items() if k != "hjemmeside"})})
        with patch("requests.get", side_effect=router(routes)):
            r = core.crawl(N, budget=core.RequestBudget(60))
        self.assertEqual(r["website"]["status"], "no_website")
        self.assertIn("no website", r["missing_fields"]["news"].lower())

    def test_web_crash_never_costs_the_registry_profile(self):
        with patch("web.enrich", side_effect=RuntimeError("boom")):
            r = self.crawl({})
        self.assertEqual(r["official_legal_name"], NAME)
        self.assertIn("Website check failed", r["missing_fields"]["news"])


class RobotsTests(unittest.TestCase):
    def setUp(self):
        web._robots_cache.clear()

    def rules(self, text):
        return web.parse_robots(text)

    def test_missing_robots_allows_everything(self):
        r = self.rules("")
        self.assertTrue(r.allows("/"))
        self.assertTrue(r.allows("/karriere"))

    def test_disallow_blocks_a_prefixed_path(self):
        r = self.rules("User-agent: *\nDisallow: /search\nDisallow: /admin/")
        self.assertFalse(r.allows("/search"))
        self.assertFalse(r.allows("/search?q=x"))
        self.assertFalse(r.allows("/admin/panel"))
        self.assertTrue(r.allows("/karriere"))

    def test_longer_allow_wins_over_disallow(self):
        r = self.rules("User-agent: *\nDisallow: /karriere\nAllow: /karriere/ledige-stillinger")
        self.assertFalse(r.allows("/karriere"))
        self.assertTrue(r.allows("/karriere/ledige-stillinger/123"))

    def test_our_agent_group_overrides_the_star_group(self):
        r = self.rules("User-agent: *\nDisallow: /\n\nUser-agent: signalpost-agent\nDisallow: /admin")
        self.assertTrue(r.allows("/karriere"))
        self.assertFalse(r.allows("/admin"))

    def test_wildcard_and_end_anchor(self):
        r = self.rules("User-agent: *\nDisallow: /*.pdf$\nDisallow: /sok*")
        self.assertFalse(r.allows("/rapport.pdf"))
        self.assertTrue(r.allows("/rapport.pdf?x=1"))
        self.assertFalse(r.allows("/sok?q=1"))

    def test_disallowed_page_is_never_fetched(self):
        pages = {"https://foo.no/robots.txt": "User-agent: *\nDisallow: /karriere",
                 "https://foo.no": "<html><body>hei</body></html>"}
        logs = []
        with patch("web.requests.get", side_effect=site(pages)), patch("web.public_host", return_value=True):
            page = web.fetch("https://foo.no/karriere", web.WebBudget(Sess(), lambda: None), logs)
        self.assertIsNone(page)
        self.assertTrue(any("robots.txt" in line for line in logs))

    def test_robots_is_fetched_once_per_host(self):
        pages = {"https://foo.no/robots.txt": "User-agent: *\nDisallow: /nei",
                 "https://foo.no/a": "<html><body>a</body></html>",
                 "https://foo.no/b": "<html><body>b</body></html>"}
        fake = site(pages)
        with patch("web.requests.get", side_effect=fake) as get, patch("web.public_host", return_value=True):
            budget = web.WebBudget(Sess(), lambda: None)
            self.assertIsNotNone(web.fetch("https://foo.no/a", budget, []))
            self.assertIsNotNone(web.fetch("https://foo.no/b", budget, []))
        calls = [c.args[0] for c in get.call_args_list]
        self.assertEqual(calls.count("https://foo.no/robots.txt"), 1)

    def test_unreachable_robots_does_not_block_the_crawl(self):
        pages = {"https://foo.no/robots.txt": requests.ConnectionError("down"),
                 "https://foo.no": "<html><body>hei</body></html>"}
        with patch("web.requests.get", side_effect=site(pages)), patch("web.public_host", return_value=True):
            page = web.fetch("https://foo.no", web.WebBudget(Sess(), lambda: None), [])
        self.assertIsNotNone(page)


class RunnerTests(unittest.TestCase):
    def test_input_file_formats(self):
        import tempfile, pathlib, run
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d, "n.txt")
            p.write_text("organisasjonsnummer\n923609016\n\n984 851 006  # DNB\n\"923609016\",x\n12345\nabc\n", encoding="utf-8")
            self.assertEqual(run.read_numbers(p), ["923609016", "984851006", "923609016", "12345", "abc"])


if __name__ == "__main__":
    unittest.main()
