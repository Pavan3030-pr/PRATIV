import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import requests

import core
import main

N = "984851006"
ENHET = {
    "organisasjonsnummer": N, "navn": "DNB BANK ASA", "stiftelsesdato": "2002-09-10",
    "organisasjonsform": {"kode": "ASA", "beskrivelse": "Allmennaksjeselskap"},
    "naeringskode1": {"kode": "64.190", "beskrivelse": "Bankvirksomhet ellers"},
    "antallAnsatte": 4000, "hjemmeside": "www.dnb.no", "registrertIMvaregisteret": True,
    "institusjonellSektorkode": {"kode": "2100", "beskrivelse": "Banker"},
    "konkurs": False, "underAvvikling": False, "underTvangsavviklingEllerTvangsopplosning": False,
    "forretningsadresse": {"adresse": ["Dronning Eufemias gate 30"], "postnummer": "0191", "poststed": "OSLO", "land": "Norge"},
}
ROLES = {"rollegrupper": [
    {"type": {"kode": "DAGL"}, "roller": [{"type": {"kode": "DAGL"}, "person": {"navn": {"fornavn": "Ola", "etternavn": "Nordmann"}}}]},
    {"type": {"kode": "STYR"}, "roller": [
        {"type": {"kode": "LEDE"}, "person": {"navn": {"fornavn": "Kari", "etternavn": "Nordmann"}}},
        {"type": {"kode": "MEDL"}, "person": {"navn": {"fornavn": "Per", "etternavn": "Hansen"}}},
        {"type": {"kode": "MEDL"}, "person": {"navn": {"fornavn": "Gone", "etternavn": "Person"}}, "fratraadt": True}]}]}
SUBS = {"_embedded": {"underenheter": [{"organisasjonsnummer": "900000001", "navn": "DNB FILIAL", "overordnetEnhet": N}]},
        "page": {"totalElements": 7}}


def account(org=N, end="2023-12-31", revenue=1000000, result=250000.0, kind="SELSKAP"):
    return {"regnskapstype": kind, "valuta": "NOK", "virksomhet": {"organisasjonsnummer": org},
            "regnskapsperiode": {"fraDato": end[:4] + "-01-01", "tilDato": end},
            "resultatregnskapResultat": {"aarsresultat": result, "driftsresultat": {
                "driftsresultat": 300000, "driftsinntekter": {"sumDriftsinntekter": revenue}}}}


def router(routes):
    """routes: {url: (status, body) | Exception}; unknown URLs return 404."""
    def fake_get(url, params=None, headers=None, timeout=None):
        route = routes.get(url, (404, {}))
        if isinstance(route, Exception):
            raise route
        status, body = route
        return Mock(status_code=status, json=lambda: body)
    return fake_get


def full_routes(**over):
    routes = {f"{core.ENHETER}/{N}": (200, ENHET), f"{core.ENHETER}/{N}/roller": (200, ROLES),
              core.UNDERENHETER: (200, SUBS), f"{core.REGNSKAP}/{N}": (200, [account()])}
    routes.update(over)
    return routes


class Base(unittest.TestCase):
    def setUp(self):
        for target, value in (("BACKOFF", (0, 0)), ("MIN_INTERVAL", 0)):
            p = patch.object(core, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch("web.public_host", return_value=False)   # tests never touch real websites
        p.start()
        self.addCleanup(p.stop)

    def crawl(self, routes, store=None, cap=50):
        with patch("core.requests.get", side_effect=router(routes)) as get:
            self.get = get
            return core.crawl(N, store=store, budget=core.RequestBudget(cap), enrich_web=False)


class CoverageAndEvidenceTests(Base):
    def test_full_profile_has_every_expected_field_with_its_own_evidence(self):
        r = self.crawl(full_routes())
        self.assertEqual(r["coverage"]["found"], r["coverage"]["expected"])
        self.assertEqual(r["profile"]["employees"], 4000)
        self.assertEqual(r["profile"]["general_manager"], "Ola Nordmann")
        self.assertEqual(r["profile"]["board_member_count"], 2)   # resigned member excluded
        self.assertEqual(r["profile"]["subunit_count"], 7)
        self.assertTrue(r["profile"]["financial_revenue"].startswith("NOK 1 000 000"))
        self.assertTrue(r["match_verified"])
        keys = {e["target_metric_key"] for e in r["lineage_evidences"]}
        self.assertEqual(keys, set(core.EXPECTED))
        for e in r["lineage_evidences"]:
            self.assertTrue(e["source_url_link"].startswith("https://data.brreg.no/"))
            self.assertEqual(len(e["value_sha256"]), 64)
            self.assertLessEqual(len(e["target_metric_key"]), 64)
            self.assertTrue(e["explanation_chain"] and e["field_path"])
            datetime.fromisoformat(e["crawl_timestamp"].replace("Z", "+00:00"))
        self.assertIn("DNB BANK ASA", r["summary"])
        self.assertEqual(r["requests_used"], 4)

    def test_registry_evidence_uses_exact_enhetsregisteret_url_for_backend_validation(self):
        r = self.crawl(full_routes())
        for e in r["lineage_evidences"]:
            if e["target_metric_key"] in ("official_legal_name", "employees", "industry", "registered_address"):
                self.assertEqual(e["source_url_link"], f"{core.ENHETER}/{N}")

    def test_accounts_of_another_company_are_never_published(self):
        r = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (200, [account(org="923609016", revenue=999)])}))
        self.assertNotIn("financial_revenue", r["profile"])
        self.assertIn("financial_revenue", r["missing_fields"])
        self.assertFalse(r["match_verified"])
        self.assertIsNone(r["financial_revenue"])

    def test_latest_parent_company_accounts_are_used(self):
        rows = [account(end="2021-12-31", revenue=1), account(end="2023-12-31", revenue=3), account(end="2024-12-31", revenue=9, kind="KONSERN")]
        r = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (200, rows)}))
        self.assertIn("2023-12-31", r["profile"]["financial_revenue"])
        self.assertEqual(r["financials"]["revenue"], 3)

    def test_multi_year_history_lists_only_this_companys_filed_years(self):
        rows = [account(end="2021-12-31", revenue=1), account(end="2023-12-31", revenue=3), account(end="2022-12-31", revenue=2),
                account(org="923609016", end="2022-12-31", revenue=999), account(end="2023-12-31", revenue=7, kind="KONSERN")]
        r = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (200, rows)}))
        hist = r["financials"]["history"]
        self.assertEqual([(h["period_end"], h["revenue"]) for h in hist], [("2023-12-31", 3), ("2022-12-31", 2), ("2021-12-31", 1)])

    def test_missing_figures_are_null_with_a_reason_never_estimated(self):
        r = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (404, {})}))
        for key in ("financial_revenue", "operating_result", "net_profit"):
            self.assertNotIn(key, r["profile"])
            self.assertIn("Regnskapsregisteret", r["missing_fields"][key])
        self.assertIsNone(r["net_profit"])

    def test_non_numeric_figure_is_not_published(self):
        bad = account()
        bad["resultatregnskapResultat"]["aarsresultat"] = "n/a"
        r = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (200, [bad])}))
        self.assertNotIn("net_profit", r["profile"])
        self.assertIn("net_profit", r["missing_fields"])

    def test_secondary_sources_failing_never_blocks_the_profile(self):
        r = self.crawl(full_routes(**{f"{core.ENHETER}/{N}/roller": (503, {}), core.UNDERENHETER: requests.Timeout("x"),
                                      f"{core.REGNSKAP}/{N}": (500, {})}))
        self.assertEqual(r["official_legal_name"], "DNB BANK ASA")
        self.assertIn("unavailable", r["missing_fields"]["general_manager"])
        self.assertEqual(sorted(r["update"]["sources_unavailable"]), ["accounts", "roles", "subunits"])

    def test_lookup_count_stays_small_enough_for_the_daily_limit(self):
        self.crawl(full_routes())
        self.assertLessEqual(self.get.call_count, 4)


class RegistryErrorTests(Base):
    def test_invalid_checksum_rejected_without_network_request(self):
        with patch("core.requests.get") as get:
            with self.assertRaises(core.CrawlError) as ctx:
                core.crawl("923609017", budget=core.RequestBudget(5))
        self.assertEqual(ctx.exception.status, 400)
        get.assert_not_called()

    def test_unknown_company_is_404_and_removed_company_is_410(self):
        for status in (404, 410):
            with self.assertRaises(core.CrawlError) as ctx:
                self.crawl({f"{core.ENHETER}/{N}": (status, {})})
            self.assertEqual(ctx.exception.status, status)

    def test_timeout_is_retried_then_reported_as_503(self):
        with self.assertRaises(core.CrawlError) as ctx:
            self.crawl({f"{core.ENHETER}/{N}": requests.Timeout("t")})
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(self.get.call_count, 3)

    def test_transient_503_then_success(self):
        answers = [Mock(status_code=503), Mock(status_code=200, json=lambda: ENHET)]
        def fake(url, **kw):
            return answers.pop(0) if url.endswith(N) and answers else Mock(status_code=404)
        with patch("core.requests.get", side_effect=fake):
            r = core.crawl(N, budget=core.RequestBudget(20))
        self.assertEqual(r["official_legal_name"], "DNB BANK ASA")

    def test_response_for_a_different_company_is_rejected(self):
        wrong = dict(ENHET, organisasjonsnummer="923609016")
        with self.assertRaises(core.CrawlError) as ctx:
            self.crawl({f"{core.ENHETER}/{N}": (200, wrong)})
        self.assertEqual(ctx.exception.status, 502)

    def test_request_budget_is_enforced(self):
        with self.assertRaises(core.CrawlError) as ctx:
            self.crawl(full_routes(), cap=0)
        self.assertEqual(ctx.exception.status, 429)
        r = self.crawl(full_routes(), cap=1)          # primary fetch only; the rest degrades
        self.assertEqual(r["requests_used"], 1)
        self.assertIn("budget", r["missing_fields"]["general_manager"])


class UpdateDetectionTests(Base):
    def test_new_then_unchanged_then_changed_with_field_diff(self):
        store = core.SnapshotStore(None)
        self.assertEqual(self.crawl(full_routes(), store)["update"]["status"], "new")
        self.assertEqual(self.crawl(full_routes(), store)["update"]["status"], "unchanged")
        changed = self.crawl(full_routes(**{f"{core.ENHETER}/{N}": (200, dict(ENHET, antallAnsatte=4100))}), store)
        self.assertEqual(changed["update"]["status"], "changed")
        self.assertEqual(changed["update"]["changed_fields"], [{"field": "employees", "old": 4000, "new": 4100}])
        self.assertEqual(self.crawl(full_routes(**{f"{core.ENHETER}/{N}": (200, dict(ENHET, antallAnsatte=4100))}), store)["update"]["status"], "unchanged")

    def test_temporary_source_outage_is_not_reported_as_a_change(self):
        store = core.SnapshotStore(None)
        self.crawl(full_routes(), store)
        down = self.crawl(full_routes(**{f"{core.REGNSKAP}/{N}": (503, {})}), store)
        self.assertEqual(down["update"]["status"], "unchanged")
        self.assertNotIn("financial_revenue", down["profile"])      # not published without fresh evidence

    def test_agent_hash_matches_every_seeded_profile_hash(self):
        rows = json.loads((Path(__file__).resolve().parent.parent / "db" / "profiles_1000.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 1000)
        for row in rows:
            payload = {k: row[k] for k in core.REGISTRY_KEYS}
            self.assertEqual(core.sha(payload), row["delta_sync_hash"], row["organisasjonsnummer"])

    def test_unchanged_registry_data_is_recognised_against_the_seeded_baseline(self):
        path = Path(__file__).resolve().parent.parent / "db" / "profiles_1000.json"
        row = json.loads(path.read_text(encoding="utf-8"))[0]
        raw = {"organisasjonsnummer": row["organisasjonsnummer"], "navn": row["navn"],
               "organisasjonsform": {"kode": row["organisasjonsform_kode"]}, "stiftelsesdato": row["stiftelsesdato"],
               "antallAnsatte": row["antallAnsatte"], "naeringskode1": {"beskrivelse": row["naeringskode1_beskrivelse"]},
               "forretningsadresse": row["forretningsadresse"]}
        store = core.SnapshotStore(None, str(path))
        number = row["organisasjonsnummer"]
        with patch("core.requests.get", side_effect=router({f"{core.ENHETER}/{number}": (200, raw)})):
            r = core.crawl(number, store=store, budget=core.RequestBudget(20))
        self.assertEqual(r["delta_sync_hash"], row["delta_sync_hash"])
        self.assertEqual(r["update"]["status"], "unchanged")
        self.assertEqual(r["update"]["compared_against"], "seeded_registry_core")
        raw["navn"] = "RENAMED AS"
        with patch("core.requests.get", side_effect=router({f"{core.ENHETER}/{number}": (200, raw)})):
            r = core.crawl(number, store=core.SnapshotStore(None, str(path)), budget=core.RequestBudget(20))
        self.assertEqual(r["update"]["status"], "changed")
        self.assertEqual(r["update"]["changed_fields"][0]["field"], "navn")


class ApiEndpointTests(Base, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")
        p = patch.object(main, "STORE", core.SnapshotStore(None))
        p.start()
        self.addCleanup(p.stop)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health_and_invalid_number(self):
        self.assertEqual((await self.client.get("/health")).json()["status"], "HEALTHY")
        with patch("core.requests.get") as get:
            self.assertEqual((await self.client.post("/api/v1/crawl/invalid123")).status_code, 400)
            self.assertEqual((await self.client.post("/api/v1/crawl/923609017")).status_code, 400)
        get.assert_not_called()

    async def test_crawl_endpoint_returns_profile_evidence_and_update_status(self):
        with patch("core.requests.get", side_effect=router(full_routes())):
            response = await self.client.post(f"/api/v1/crawl/{N}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["official_legal_name"], "DNB BANK ASA")
        self.assertEqual(body["update"]["status"], "new")
        self.assertEqual(body["coverage"]["found"], 17)
        self.assertEqual(len(body["delta_sync_hash"]), 64)

    async def test_registry_not_found_and_timeout_status_codes(self):
        with patch("core.requests.get", side_effect=router({f"{core.ENHETER}/{N}": (404, {})})):
            self.assertEqual((await self.client.post(f"/api/v1/crawl/{N}")).status_code, 404)
        with patch("core.requests.get", side_effect=router({f"{core.ENHETER}/{N}": requests.Timeout("t")})):
            self.assertEqual((await self.client.post(f"/api/v1/crawl/{N}")).status_code, 503)


if __name__ == "__main__":
    unittest.main()
