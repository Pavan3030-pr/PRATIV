"""Website enrichment for the Signalpost agent: website ownership check, social links, news, jobs.

Rules (each one answers an audit finding):
  1. The registry's website is only used for social links, news and jobs after the site itself shows
     this company's organisation number (preferred) or its exact registered name with no group/sister
     signals. A parent-group or brand site fails that check, is reported as not verified, and nothing
     is taken from it.
  2. A social account is published only if its handle matches the company (its legal name or its own
     verified domain). Footer links of the parent group, the web agency, the website theme, share
     buttons and personal profiles never match and are discarded.
  3. A news item must be a real post: its own page on the same site, a human title (not a menu label
     like "See more news"), not a product/service page, and a publish date taken from a publish
     field (time[datetime], datePublished, RSS pubDate, Atom published). "modified", "updated",
     dateModified, lastBuildDate and Atom <updated> are never used as a publish date.
  4. Job postings are taken only from a verified own site (careers / ledige stillinger links), with
     a human title and same-site URL. Nothing is guessed.
Everything else stays empty with a stated reason; nothing is guessed.
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:  # defusedxml protects against entity-expansion attacks in untrusted feeds
    from defusedxml import ElementTree as SafeET
except ImportError:  # pragma: no cover
    SafeET = None

WEB_HEADERS = {"User-Agent": "signalpost-agent/3.1 (Builderr Signalpost entry; +https://github.com/Pavan3030-pr/PRATIV)",
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
               "Accept-Language": "nb,no;q=0.9,en;q=0.7"}
WEB_TIMEOUT = 8
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 4
MAX_WEB_REQUESTS = 10          # per company, retries included: keeps 100 companies far inside the daily limit
MAX_NEWS = 5
MAX_JOBS = 8

LEGAL_FORMS = {"as", "asa", "ans", "da", "ba", "sa", "ks", "nuf", "enk", "iks", "sf", "stift", "ltd", "ab", "oy", "gmbh"}
PAGE_HINT = re.compile(r"(kontakt|contact|om-oss|omoss|about|personvern|privacy|vilkar|vilk%c3%a5r|terms|betingelser|impressum|cookie|handelsbetingelser)", re.I)
NEWS_HINT = re.compile(r"^/(nyheter|nyhet|nytt|news|aktuelt|aktuelle-saker|blogg|blog|presse|pressemeldinger|press|artikler|nyhetsarkiv|siste-nytt)/?$", re.I)
JOB_HINT = re.compile(
    r"(karriere|careers?|\bjobb\w*|\bjobs?|ledige[-_/ ]?stillinger|\bstilling(er)?|vacancies|"
    r"join[-_ ]?us|work[-_ ]?with[-_ ]?us|ledige[-_ ]?jobber)",
    re.I,
)
JOB_LABEL = re.compile(
    r"^(karriere|careers?|jobb\w*|ledige stillinger|ledige jobber|vacancies|"
    r"open positions|job openings|join us|work with us)$",
    re.I,
)
JOB_MENU = re.compile(
    r"^(see all|se alle|vis alle|more jobs|flere stillinger|all jobs|alle stillinger|ledige stillinger|"
    r"se alle jobber|see all jobs|ledige jobber|open positions|vacancies|careers?|karriere|jobs?)$",
    re.I,
)
PRODUCT_PATH = re.compile(r"/(produkt|produkter|product|products|shop|butikk|nettbutikk|handlekurv|cart|tjeneste|tjenester|service|services|"
                          r"category|kategori|tag|tags|author|forfatter|kontakt|contact|om-oss|about|login|search|sok|page)(/|$)", re.I)
MENU_LABEL = re.compile(r"^(see|view|read|show|vis|se|les|last|load|flere|more|alle|all|go to|g[åa] til)?\s*"
                        r"(flere|more|alle|all|mer|older|eldre|neste|next|forrige|previous|siste)?\s*"
                        r"(nyheter|news|saker|artikler|articles|posts|innlegg|blog|blogg|aktuelt|presse|press|pressemeldinger|"
                        r"mer|more|nyhetsarkiv|archive|arkiv|stories)?\s*(→|>|»|\.\.\.)?$", re.I)
MODIFIED_HINT = re.compile(r"(modif|updated|update|oppdat|endret|lastmod|revised|sist\s+endret)", re.I)
PUBLISHED_ATTR = re.compile(r"(^|[-_ ])(date|dato|published|posted|post-date|entry-date|pubdate)($|[-_ ])", re.I)

# Accounts that are never the company's: platform pages, share/intent endpoints, theme / builder / agency defaults.
RESERVED = {"sharer", "sharer.php", "share", "share.php", "dialog", "plugins", "tr", "intent", "home", "explore", "hashtag", "search",
            "login", "signup", "policies", "help", "about", "legal", "privacy", "pages", "p", "reel", "reels", "stories", "accounts",
            "watch", "feed", "shareArticle", "company", "in", "pub", "groups", "events", "people", "profile.php", "settings", "i",
            "oauth", "tiktok", "embed", "playlist", "results", "shorts", "channel", "feed", "gaming", "music", "premium", "podcasts", "live", "hashtag", "videos", "iframe_api", "facebook", "instagram", "linkedin", "twitter", "x", "youtube", "wordpress", "wix", "squarespace",
            "shopify", "elementor", "envato", "themeforest", "elegantthemes", "divi", "godaddy", "jimdo", "webflow", "weebly"}
SOCIAL_PATTERNS = {
    "facebook": (re.compile(r"^(?:[a-z]{2}-[a-z]{2}\.|www\.|m\.)?facebook\.com$"), r"^/([A-Za-z0-9.\-_]{3,})/?$", "https://www.facebook.com/{h}"),
    "instagram": (re.compile(r"^(?:www\.)?instagram\.com$"), r"^/([A-Za-z0-9._]{2,})/?$", "https://www.instagram.com/{h}"),
    "linkedin": (re.compile(r"^(?:[a-z]{2}\.|www\.)?linkedin\.com$"), r"^/(?:company|school)/([^/?#]{2,})/?$", "https://www.linkedin.com/company/{h}"),
    "x": (re.compile(r"^(?:www\.|mobile\.)?(?:twitter|x)\.com$"), r"^/([A-Za-z0-9_]{2,15})/?$", "https://x.com/{h}"),
    "youtube": (re.compile(r"^(?:www\.|m\.)?youtube\.com$"), r"^/(@[A-Za-z0-9._\-]{3,}|c/[^/?#]+|user/[^/?#]+|[A-Za-z0-9_\-]{3,})/?$", "https://www.youtube.com/{h}"),
    "tiktok": (re.compile(r"^(?:www\.)?tiktok\.com$"), r"^/(@[A-Za-z0-9._]{2,})/?$", "https://www.tiktok.com/{h}"),
}
MONTHS = {"januar": 1, "jan": 1, "january": 1, "februar": 2, "feb": 2, "february": 2, "mars": 3, "mar": 3, "march": 3,
          "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "jun": 6, "june": 6, "juli": 7, "jul": 7, "july": 7,
          "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "october": 10, "oct": 10,
          "november": 11, "nov": 11, "desember": 12, "des": 12, "december": 12, "dec": 12}


# --------------------------------------------------------------------------- helpers
def fold(text: str) -> str:
    """Lower-case, strip accents, map Norwegian letters, keep only a-z0-9."""
    text = text.casefold().replace("æ", "ae").replace("ø", "o").replace("å", "a")
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9]", "", text)


def normalize_url(raw: Any) -> Optional[str]:
    """Registry 'hjemmeside' values are free text: take the first plausible host, add a scheme."""
    if not isinstance(raw, str):
        return None
    for token in re.split(r"[\s,;]+", raw.strip()):
        if not token or "@" in token and "/" not in token:
            continue
        url = token if re.match(r"^https?://", token, re.I) else "https://" + token.lstrip("/")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme in ("http", "https") and "." in host and re.fullmatch(r"[a-z0-9.\-æøå]+", host):
            return url
    return None


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, base: str) -> bool:
    h, b = host_of(url), host_of(base)
    return bool(h) and (h == b or h.endswith("." + b))


def public_host(host: str) -> bool:
    """Refuse localhost / private networks: registry values are untrusted input."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    try:
        return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
    except ValueError:
        return False


def parse_date(text: Any) -> Optional[date]:
    if not isinstance(text, str):
        return None
    t = text.strip().casefold()
    cands: List[Tuple[int, int, int]] = []
    if m := re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", t):
        cands.append((int(m[1]), int(m[2]), int(m[3])))
    elif m := re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)", t):
        cands.append((int(m[3]), int(m[2]), int(m[1])))
    elif m := re.search(r"(?<!\d)(\d{1,2})\.?\s+([a-zæøå]+)\.?,?\s+(\d{4})(?!\d)", t):
        if m[2] in MONTHS:
            cands.append((int(m[3]), MONTHS[m[2]], int(m[1])))
    elif m := re.search(r"([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", t):
        if m[1] in MONTHS:
            cands.append((int(m[3]), MONTHS[m[1]], int(m[2])))
    else:
        try:
            dt = parsedate_to_datetime(text.strip())
            cands.append((dt.year, dt.month, dt.day))
        except (TypeError, ValueError, IndexError):
            pass
    for y, mo, d in cands:
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def valid_publish_date(d: Optional[date], today: date) -> bool:
    return d is not None and date(2000, 1, 1) <= d <= today + timedelta(days=1)


class WebBudget:
    """Per-company cap on website requests, on top of the run-wide budget."""
    def __init__(self, sess: Any, throttle: Callable[[], None], limit: int = MAX_WEB_REQUESTS):
        self.sess, self.throttle, self.limit, self.used = sess, throttle, limit, 0

    def spend(self) -> bool:
        if self.used >= self.limit:
            return False
        self.sess.budget.take()          # may raise core.CrawlError(429): handled by the caller
        self.sess.calls += 1
        self.used += 1
        self.throttle()
        return True


class RobotsRules:
    """The subset of robots.txt this crawler needs: Allow/Disallow for `*` and for our own agent."""

    def __init__(self, groups: Dict[str, List[Tuple[bool, str]]]):
        self.rules = groups.get("signalpost-agent") or groups.get("*") or []

    def allows(self, path: str) -> bool:
        path = path or "/"
        best_len, allowed = -1, True
        for is_allow, pattern in self.rules:
            if pattern == "":
                continue
            anchored = pattern.endswith("$")
            body = pattern[:-1] if anchored else pattern
            regex = "^" + ".*".join(re.escape(part) for part in body.split("*")) + ("$" if anchored else "")
            if re.match(regex, path, re.I) and len(pattern) >= best_len:
                best_len, allowed = len(pattern), is_allow
        return allowed


def parse_robots(text: str) -> RobotsRules:
    groups: Dict[str, List[Tuple[bool, str]]] = {}
    agents: List[str] = []
    in_rules = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = line.split(":", 1)
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if in_rules:  # a new agent block starts
                agents, in_rules = [], False
            agents.append(value.lower().split("/")[0])
            in_rules = False
        elif field in ("allow", "disallow"):
            in_rules = True
            for agent in agents or ["*"]:
                groups.setdefault(agent, []).append((field == "allow", value))
    return RobotsRules(groups)


ROBOTS_UNSET = object()
_robots_cache: Dict[str, Any] = {}


def robots_rules(scheme: str, host: str) -> RobotsRules:
    """Fetch and cache /robots.txt once per host. An unreachable or missing file allows crawling."""
    key = f"{scheme}://{host}"
    cached = _robots_cache.get(key, ROBOTS_UNSET)
    if cached is not ROBOTS_UNSET:
        return cached  # type: ignore[return-value]
    rules = RobotsRules({})
    if len(_robots_cache) > 500:  # a long crawl over many hosts must not grow without bound
        _robots_cache.clear()
    try:
        resp = requests.get(f"{key}/robots.txt", headers=WEB_HEADERS, timeout=WEB_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            rules = parse_robots(resp.text[:200_000])
    except requests.RequestException:
        pass
    _robots_cache[key] = rules
    return rules


class Page:
    def __init__(self, url: str, text: str, ctype: str):
        self.url, self.text, self.ctype = url, text, ctype
        self._soup: Optional[BeautifulSoup] = None

    @property
    def soup(self) -> BeautifulSoup:
        if self._soup is None:
            self._soup = BeautifulSoup(self.text, "html.parser")
        return self._soup


def fetch(url: str, budget: WebBudget, logs: List[str]) -> Optional[Page]:
    """GET one public page with manual redirects (each hop re-checked), size and type limits."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        host = urlparse(current).hostname or ""
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https") or not public_host(host):
            logs.append(f"Website: refused to fetch {current} (not a public http(s) host).")
            return None
        if not robots_rules(parsed.scheme, host).allows(parsed.path or "/"):
            logs.append(f"Website: {parsed.path or '/'} is disallowed by {host}/robots.txt; skipped.")
            return None
        if not budget.spend():
            logs.append("Website: per-company request limit reached; remaining pages skipped.")
            return None
        try:
            resp = requests.get(current, headers=WEB_HEADERS, timeout=WEB_TIMEOUT, allow_redirects=False, stream=True)
        except requests.RequestException as exc:
            logs.append(f"Website: {current} unreachable ({exc.__class__.__name__}).")
            return None
        try:
            status = resp.status_code
            if status in (301, 302, 303, 307, 308):
                target = (getattr(resp, "headers", {}) or {}).get("Location")
                if not target:
                    return None
                current = urljoin(current, target)
                continue
            if status != 200:
                logs.append(f"Website: {current} returned HTTP {status}.")
                return None
            ctype = ((getattr(resp, "headers", {}) or {}).get("Content-Type") or "").lower()
            if ctype and not re.search(r"(html|xml|json|text)", ctype):
                return None
            chunks, size = [], 0
            for chunk in resp.iter_content(65536):
                size += len(chunk)
                chunks.append(chunk)
                if size > MAX_BYTES:
                    break
            raw = b"".join(chunks)[:MAX_BYTES]
            enc = getattr(resp, "encoding", None) if "charset" in ctype else None
            try:
                text = raw.decode(enc or "utf-8", errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return Page(current, text, ctype)
        finally:
            close = getattr(resp, "close", None)
            if callable(close):
                close()
    logs.append(f"Website: too many redirects for {url}.")
    return None


# --------------------------------------------------------------------------- 1. ownership check
def _page_text(page: Page) -> str:
    soup = page.soup
    parts = [soup.get_text(" ")]
    for s in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        parts.append(s.string or s.get_text())
    parts.append(" ".join(m.get("content", "") for m in soup.find_all("meta") if m.get("content")))
    return re.sub(r"\s+", " ", " ".join(parts).replace("\xa0", " "))


def org_number_pattern(n: str) -> "re.Pattern[str]":
    return re.compile(r"(?<!\d)" + n[:3] + r"[ .\-]?" + n[3:6] + r"[ .\-]?" + n[6:] + r"(?!\d)")


def name_pattern(name: str) -> Optional["re.Pattern[str]"]:
    tokens = re.findall(r"\w+", name.casefold())
    if len("".join(tokens)) < 4:
        return None
    return re.compile(r"(?<!\w)" + r"[\s.,/\-&]*".join(re.escape(t) for t in tokens) + r"(?!\w)", re.I)


GENERIC_NAME_TOKENS = {"norge", "norsk", "norske", "nordic", "nordisk", "group", "gruppe", "gruppen", "holding",
                      "konsern", "sameie", "sameiet", "borettslag", "borettslaget", "forening", "foreningen", "lag",
                      "eiendom", "eiendommen", "drift", "service", "services", "selskap", "selskapet", "company",
                      "international", "avdeling", "division", "nord", "sor", "ost", "vest"}
# A group or sister-company page that merely mentions the legal name. Deliberately generic: no company names.
GROUP_SIGNALS = re.compile(
    r"\b(konsern|morselskap|datterselskap|s\u00f8sterselskap|sosterselskap|sister\s+compan|parent\s+compan|"
    r"part\s+of\s+the\s+[\w\-]+\s+group|group\s+of\s+companies|our\s+companies|v\u00e5re\s+selskaper)\b",
    re.I,
)


def domain_matches_name(host: str, name: str) -> bool:
    """Does the site's own host look like this company (foo.no for Foo Norge AS, acmebygg.no for Acme Bygg AS)?

    A registry value can point at the parent group or a sister company (rekonstrukt.no or obos.no for a company that
    merely belongs to that group). Tying every published fact to the company's own name or organisation number is the
    rule, so a site whose domain has nothing to do with the name is never accepted, even if the name appears on it.
    """
    raw = (urlparse(host).hostname or "") if "//" in host else host
    labels = [fold(p) for p in raw.lower().split(".")]
    labels = [l for l in labels if len(l) >= 3]
    if not labels:
        return False
    for token in re.split(r"\s+", name.strip()):
        t = fold(token)
        if len(t) < 3 or t in GENERIC_NAME_TOKENS or t in LEGAL_FORMS:
            continue
        for label in labels:
            if t == label or (len(t) >= 4 and label.startswith(t)) or (len(label) >= 4 and t.startswith(label)) \
                    or (len(t) >= 4 and t in label):
                return True
    return False


def verify_ownership(page: Page, number: str, name: str) -> Optional[str]:
    """True only when the host is this company's own and the page proves it by org number or exact legal name."""
    text = _page_text(page)
    if not domain_matches_name(urlparse(page.url).hostname or "", name):
        return None
    if org_number_pattern(number).search(text):
        return "organisation_number"
    pat = name_pattern(name)
    if not pat or not pat.search(text):
        return None
    if GROUP_SIGNALS.search(text):
        return None
    tokens = re.findall(r"\w+", name.casefold())
    core = [t for t in tokens if t not in LEGAL_FORMS]
    return "exact_legal_name" if "".join(core) else None


def candidate_pages(page: Page, limit: int = 3) -> List[str]:
    out: List[str] = []
    for a in page.soup.find_all("a", href=True):
        url = urljoin(page.url, a["href"].split("#")[0])
        path = urlparse(url).path
        if url in out or url == page.url or not same_site(url, page.url) or not PAGE_HINT.search(path + " " + a.get_text(" ")):
            continue
        out.append(url)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- 2. social links
PUBLIC_SLD = {"co", "com", "org", "net", "ac", "gov", "edu"}


def own_domain_keys(site_host: str) -> Dict[str, str]:
    """Keys derived from the verified site's host. A subdomain such as bjorkelangen.speiding.no belongs to a local unit of
    speiding.no, so its own label is 'bjorkelangen': the parent's 'speiding' must never count as this company's name."""
    labels = [l for l in site_host.lower().split(".") if l and l != "www"]
    if len(labels) < 2:
        return {}
    cut = 3 if len(labels) >= 3 and labels[-2] in PUBLIC_SLD else 2
    registrable, extra = labels[-cut:], labels[:-cut]
    keys: Dict[str, str] = {}
    if extra:
        keys[fold(extra[-1])] = "own verified website subdomain"
        keys[fold(".".join(extra))] = "own verified website subdomain"
    else:
        keys[fold(registrable[0])] = "own verified website domain"
        keys[fold(".".join(registrable))] = "own verified website domain"
    keys.pop("", None)
    return keys


def name_keys(name: str, site_host: str) -> Dict[str, str]:
    """Keys a social handle may equal. Deliberately narrow: legal name (with/without legal form) or the verified site's own domain."""
    tokens = re.findall(r"\w+", name.casefold())
    core_tokens = tokens[:]
    while core_tokens and core_tokens[-1] in LEGAL_FORMS:
        core_tokens.pop()
    keys = {}
    if core_tokens:
        keys[fold("".join(core_tokens))] = "company name"
    keys[fold("".join(tokens))] = "company name"
    for k, v in own_domain_keys(site_host).items():
        keys.setdefault(k, v)
    keys.pop("", None)
    return keys


def handle_variants(handle: str) -> List[str]:
    h = handle.lstrip("@")
    h = re.sub(r"[-_]?\d{4,}$", "", h)        # LinkedIn slugs end in numeric ids
    f = fold(h)
    variants = {f}
    for suffix in sorted(LEGAL_FORMS | {"official"}, key=len, reverse=True):
        if f.endswith(suffix) and len(f) > len(suffix) + 2:
            variants.add(f[: -len(suffix)])
    variants.discard("")
    return sorted(variants)


def social_candidates(page: Page) -> List[str]:
    urls = [urljoin(page.url, a["href"]) for a in page.soup.find_all("a", href=True)]
    for s in page.soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(s.string or s.get_text() or "null")
        except ValueError:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                same = cur.get("sameAs")
                if isinstance(same, str):
                    urls.append(same)
                elif isinstance(same, list):
                    urls += [u for u in same if isinstance(u, str)]
                stack += [v for v in cur.values() if isinstance(v, (dict, list))]
            elif isinstance(cur, list):
                stack += cur
    return urls


def extract_social(pages: List[Page], name: str, site_host: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    keys = name_keys(name, site_host)
    found: Dict[str, Dict[str, Any]] = {}
    rejected: List[str] = []
    for page in pages:
        for url in social_candidates(page):
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            for platform, (host_re, path_re, canon) in SOCIAL_PATTERNS.items():
                if not host_re.match(host):
                    continue
                m = re.match(path_re, re.sub(r"/+$", "", parsed.path) or "/")
                if not m:
                    rejected.append(f"{platform}:{url} (not a profile page)")
                    break
                handle = m.group(1)
                if handle.casefold() in RESERVED or platform in found:
                    break
                core_handle = handle.split("/", 1)[-1] if platform == "youtube" and "/" in handle else handle
                match = next((keys[v] for v in handle_variants(core_handle) if v in keys), None)
                if match:
                    found[platform] = {"platform": platform, "url": canon.format(h=handle), "handle": handle.lstrip("@"),
                                       "found_on": page.url, "matched": f"handle equals {match}"}
                else:
                    msg = f"{platform}:{handle} (handle does not match this company)"
                    if msg not in rejected:
                        rejected.append(msg)
                break
    return list(found.values()), rejected


# --------------------------------------------------------------------------- 3. news
def _is_modified_tag(tag: Any) -> bool:
    attrs = " ".join(str(tag.get(k, "")) if not isinstance(tag.get(k), list) else " ".join(tag.get(k))
                     for k in ("class", "itemprop", "property", "id", "data-type"))
    if MODIFIED_HINT.search(attrs):
        return True
    prev = tag.previous_sibling
    lead = (prev if isinstance(prev, str) else getattr(prev, "get_text", lambda *_: "")(" ") or "")[-25:]
    return bool(MODIFIED_HINT.search(lead + " " + tag.get_text(" ")[:15]))


def _date_nodes(root: Any) -> List[Any]:
    nodes = [t for t in root.find_all("time") if not _is_modified_tag(t)]
    for t in root.find_all(True, class_=PUBLISHED_ATTR):
        if t.name != "time" and not t.find("time") and len(t.get_text(strip=True)) < 40 \
                and parse_date(t.get_text(" ")) and not _is_modified_tag(t):
            nodes.append(t)
    return nodes


def _clean_title(text: str, date_text: str = "") -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    if date_text:
        text = text.replace(date_text.strip(), "").strip(" -–|·:")
    return text


def valid_title(title: str) -> bool:
    words = title.split()
    return len(title) >= 15 and len(words) >= 3 and not MENU_LABEL.match(title.strip())


def valid_article_url(url: str, site: str, listing: str) -> bool:
    p = urlparse(url)
    path = p.path.rstrip("/")
    if not same_site(url, site) or not path or url.rstrip("/") == listing.rstrip("/") or NEWS_HINT.match(path + "/"):
        return False
    return not PRODUCT_PATH.search(path + "/") and (path.count("/") >= 2 or "-" in path.rsplit("/", 1)[-1] or re.search(r"\d", path))


def _pick_anchor(container: Any, base: str) -> Optional[Tuple[str, str]]:
    best = None
    for a in container.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        heading = a.find(re.compile("^h[1-4]$")) or a.find_parent(re.compile("^h[1-4]$"))
        text = _clean_title((heading or a).get_text(" "))
        if not text:
            continue
        rank = (1 if heading else 0, len(text))
        if best is None or rank > best[0]:
            best = (rank, urljoin(base, href), text)
    return (best[1], best[2]) if best else None


def news_from_html(page: Page, site: str, today: date) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node in _date_nodes(page.soup):
        raw = node.get("datetime") or node.get_text(" ")
        d = parse_date(raw)
        if not valid_publish_date(d, today):
            continue
        picked, container = None, node.find_parent("a")
        if container is not None and container.get("href"):
            href = container["href"].strip()
            heading = container.find(re.compile("^h[1-4]$"))
            picked = (urljoin(page.url, href), _clean_title((heading or container).get_text(" "), node.get_text(" ")))
        else:
            cur = node
            for _ in range(5):
                cur = cur.parent
                if cur is None or cur.name in ("body", "html", "main", "section", "ul", "ol"):
                    break
                if len(_date_nodes(cur)) > 1:
                    break
                picked = _pick_anchor(cur, page.url)
                if picked:
                    break
        if not picked:
            continue
        url, title = picked
        title = _clean_title(title, node.get_text(" "))
        if valid_title(title) and valid_article_url(url, site, page.url):
            out.append({"title": title, "url": url.split("#")[0], "published_at": d.isoformat(), "source": "html time/date element",
                        "found_on": page.url})
    out += news_from_jsonld(page, site, today)
    return out


def news_from_jsonld(page: Page, site: str, today: date) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in page.soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(s.string or s.get_text() or "null")
        except ValueError:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack += cur
            elif isinstance(cur, dict):
                kinds = cur.get("@type")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                if any(k in ("NewsArticle", "BlogPosting", "Article", "Report") for k in kinds):
                    title = cur.get("headline") or cur.get("name")
                    main = cur.get("mainEntityOfPage")
                    url = cur.get("url") or (main if isinstance(main, str) else (main or {}).get("@id") if isinstance(main, dict) else None)
                    d = parse_date(cur.get("datePublished"))        # never dateModified
                    if isinstance(title, str) and isinstance(url, str) and valid_publish_date(d, today):
                        url, title = urljoin(page.url, url), _clean_title(title)
                        if valid_title(title) and valid_article_url(url, site, page.url):
                            out.append({"title": title, "url": url, "published_at": d.isoformat(), "source": "JSON-LD datePublished",
                                        "found_on": page.url})
                stack += [v for v in cur.values() if isinstance(v, (dict, list))]
    return out


def news_from_feed(page: Page, site: str, today: date) -> List[Dict[str, Any]]:
    if SafeET is None:
        return []
    try:
        root = SafeET.fromstring(page.text.encode("utf-8"))
    except Exception:  # malformed or hostile XML
        return []
    local = lambda el: el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""
    out: List[Dict[str, Any]] = []
    for item in root.iter():
        if local(item) not in ("item", "entry"):
            continue
        fields: Dict[str, str] = {}
        link = None
        for child in item:
            tag = local(child)
            if tag == "link":
                href = child.get("href")
                if href and child.get("rel", "alternate") == "alternate":
                    link = href
                elif child.text and child.text.strip():
                    link = child.text.strip()
            elif tag in ("title", "pubdate", "published", "date"):    # 'date' = dc:date; 'updated' is deliberately ignored
                fields[tag] = (child.text or "").strip()
        d = parse_date(fields.get("pubdate") or fields.get("published") or fields.get("date"))
        title = _clean_title(fields.get("title", ""))
        if link and valid_publish_date(d, today) and valid_title(title):
            link = urljoin(page.url, link)
            if valid_article_url(link, site, page.url):
                out.append({"title": title, "url": link, "published_at": d.isoformat(), "source": "feed publish date", "found_on": page.url})
    return out


def find_feed(page: Page) -> Optional[str]:
    feeds = []
    for l in page.soup.find_all("link", href=True):
        rel = " ".join(l.get("rel") or []).lower()
        if "alternate" in rel and re.search(r"(rss|atom)\+xml", (l.get("type") or "").lower()):
            href = urljoin(page.url, l["href"])
            if not re.search(r"comment", href + (l.get("title") or ""), re.I):
                feeds.append(href)
    feeds.sort(key=lambda u: 0 if re.search(r"(news|nyhet|blog|aktuelt|post|artik)", u, re.I) else 1)
    return feeds[0] if feeds else None


NEWS_LABEL = re.compile(r"^(nyheter|nyhet|news|aktuelt|siste nytt|latest news|news & media|news and media|presse|press|pressemeldinger|press releases|blogg|blog|media)$", re.I)


def find_news_page(page: Page) -> Optional[str]:
    """Best link to a news/blog listing: a root-level news path first, then any shallow path or link label that says news."""
    best = None
    for a in page.soup.find_all("a", href=True):
        url = urljoin(page.url, a["href"].split("#")[0].split("?")[0])
        if not same_site(url, page.url):
            continue
        path = urlparse(url).path or "/"
        if NEWS_HINT.match(path):
            return url
        last = path.rstrip("/").rsplit("/", 1)[-1]
        shallow = path.rstrip("/").count("/") <= 3
        if best is None and shallow and (NEWS_HINT.match("/" + last + "/") or NEWS_LABEL.match(re.sub(r"\s+", " ", a.get_text(" ")).strip())):
            best = url
    return best


def dedupe_news(items: List[Dict[str, Any]], today: date) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i["published_at"], reverse=True):
        key = it["url"].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    # a block of items all "published today" is a dynamic page clock, not a post date
    if len(out) >= 3 and all(i["published_at"] == today.isoformat() for i in out):
        return []
    return out[:MAX_NEWS]


# --------------------------------------------------------------------------- 4. jobs
# A posting title names a role or the act of hiring. Generic words such as "jobb" are deliberately absent:
# careers landing pages use them for culture/FAQ sections ("Balanse mellom jobb og fritid"), not for postings.
JOB_TITLE_HINT = re.compile(
    r"\b(stilling|stillinger|s\u00f8ker|s\u00f8knad|soknad|ledig|ledige|vacanc|position|ingeni\u00f8r|utvikler|"
    r"selger|mekaniker|operat\u00f8r|sj\u00e5f\u00f8r|prosjektleder|leder|assistent|medarbeider|l\u00e6rling|trainee|"
    r"praktikant|sommervikar|tilkallingshjelp|konsulent|tekniker|mont\u00f8r|snekker|elektriker|r\u00e5dgiver|"
    r"spesialist|koordinator|sjef|direkt\u00f8r|fagarbeider|h\u00e5ndverker|servit\u00f8r|kokk|renholder|vekter|"
    r"resepsjonist|sekret\u00e6r|\u00f8konom|regnskapsf\u00f8rer|l\u00e6rer|sykepleier|barnehagel\u00e6rer|butikkmedarbeider|"
    r"engineer|developer|manager|consultant|analyst|designer|technician|coordinator|director|officer|"
    r"advisor|accountant|driver|operator|apprentice|receptionist|recruiter|architect|scientist|researcher|controller)\b",
    re.I,
)
# A notice or a careers article, not a vacancy. Matching on the prefix matters: boards append the location,
# so "Open søknad produksjon Ørsta" must be rejected just like "Åpen søknad".
# "Sjekk ledige stillinger", "See open positions": an invitation to browse, not a vacancy.
JOB_CALL_TO_ACTION = re.compile(
    r"^(sjekk|se|finn|utforsk|bla|check|see|browse|view|explore|find)\b.*"
    r"\b(ledige|stillinger|stilling|\w*jobb\w*|jobs?|vacanc\w*|positions?|roller|roles|opportunit\w*|karriere|careers?)\b",
    re.I,
)
JOB_NOT_A_POSTING = re.compile(
    r"^((\u00e5pen|apen|open)\s+(s\u00f8knad|soknad|application)|spontan(s\u00f8knad|soknad)?|"
    r"send (us )?(an )?application|contact us|kontakt oss)\b",
    re.I,
)
JOB_ARTICLE = re.compile(r"^(veien til|slik (blir|f\u00e5r|s\u00f8ker|er)|hva er|alt du|les mer|mer om|om \u00e5)\b", re.I)
NOTICE_PATH = re.compile(r"/(page|tag|tags|category|kategori|author|forfatter|feed|wp-json|sitemap)(/|$)", re.I)
# Postings that the company links from its own careers page but hosts on a recruitment service.
# Only a single posting URL matches; list pages and service home pages never do.
ATS_POSTING = [
    re.compile(r"^https://[\w.-]+\.teamtailor\.com/jobs/\d+", re.I),
    re.compile(r"^https://[\w.-]+\.recruitee\.com/o/[^/?#]+/?$", re.I),
    re.compile(r"^https://[\w.-]+\.webcruiter\.no/(?:[^/?#]+/)+ad/\d+", re.I),
    re.compile(r"^https://(?:www\.)?jobbnorge\.no/ledige-stillinger/stilling/\d+", re.I),
    re.compile(r"^https://[\w.-]+\.easycruit\.com/(?:[^/?#]+/)?vacancy/\d+", re.I),
    re.compile(r"^https://[\w.-]+\.talentech\.com/(?:[^/?#]+/)?job/\d+", re.I),
    re.compile(r"^https://(?:www\.)?finn\.no/job/ad/\d+", re.I),
]


def is_ats_posting(url: str) -> bool:
    return any(p.search(url) for p in ATS_POSTING)


# Employer-scoped job-board listings a company links to instead of hosting its own list.
JOB_BOARD_LISTING = [
    re.compile(r"^https://(?:www\.)?jobbnorge\.no/(?:[a-z]{2}/)?(?:search|ledige-stillinger)(?:/[^?#]*)?\?[^#]*\bemployer=\d+", re.I),
    re.compile(r"^https://(?:www\.)?finn\.no/job/employer/company/\d+", re.I),
    re.compile(r"^https://(?:www\.)?finn\.no/job/employer/\d+", re.I),
]
JOB_BOARD_POSTING = [
    re.compile(r"^https://(?:www\.)?jobbnorge\.no/(?:[a-z]{2}/)?ledige-stillinger/stilling/\d+", re.I),
    re.compile(r"^https://(?:www\.)?finn\.no/job/ad/\d+", re.I),
]


def is_job_board_listing(url: str) -> bool:
    return any(p.search(url) for p in JOB_BOARD_LISTING)


def is_job_board_posting(url: str) -> bool:
    return any(p.search(url) for p in JOB_BOARD_POSTING)

SITEMAP_MAX = 3


def sitemap_urls(home: Page, budget: "WebBudget", logs: List[str]) -> List[str]:
    """Page URLs from /sitemap.xml (and up to two child sitemaps). Bounded, best-effort, never fails the run."""
    queue = [urljoin(home.url.rstrip("/") + "/", "sitemap.xml")]
    seen: set = set()
    out: List[str] = []
    fetched = 0
    while queue and fetched < SITEMAP_MAX and budget.used < budget.limit:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        page = fetch(current, budget, logs)
        if page is None:
            continue
        fetched += 1
        locs = [html.unescape(m) for m in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", page.text, re.I)]
        if re.search(r"<sitemapindex", page.text, re.I):
            queue += [u for u in locs if u not in seen][: max(0, SITEMAP_MAX - fetched)]
        else:
            out += locs
    if out:
        logs.append(f"Website: sitemap listed {len(out)} page URL(s) ({fetched} sitemap request(s)).")
    return out[:5000]


def find_jobs_page(pages: List[Page]) -> Optional[str]:
    """Best same-site careers / vacancies link on any page already fetched from the verified site."""
    best = None
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            url = urljoin(page.url, a["href"].split("#")[0].split("?")[0])
            if not same_site(url, page.url):
                continue
            path = urlparse(url).path or "/"
            if JOB_HINT.search(path):
                return url
            label = re.sub(r"\s+", " ", a.get_text(" ")).strip()
            shallow = path.rstrip("/").count("/") <= 3
            if best is None and shallow and (JOB_HINT.search("/" + path.rstrip("/").rsplit("/", 1)[-1] + "/") or JOB_LABEL.match(label)):
                best = url
    return best


def _inside_navigation(a: Any) -> bool:
    """Menu, breadcrumb, header and footer links are navigation, never a job posting."""
    cur = a
    for _ in range(8):
        cur = cur.parent
        if cur is None:
            return False
        if getattr(cur, "name", None) in ("nav", "header", "footer"):
            return True
        marks = " ".join(cur.get("class") or []) + " " + (cur.get("id") or "")
        if re.search(r"(menu|navbar|nav-|breadcrumb|site-header|site-footer|footer|sidebar|pagination)", marks, re.I):
            return True
    return False


def clean_job_title(title: str) -> str:
    """Remove board decoration that is not part of the role: an inline location and a trailing CTA."""
    t = re.sub(r"\s+", " ", title).strip()
    t = re.split(r"\s+Location\s*:", t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"[\s,–-]+(read more|les mer|se stilling|view job|apply now|æ søk)\.?$", "", t, flags=re.I)
    return t.strip(" -–|")


def valid_job_title(title: str) -> bool:
    t = re.sub(r"\s+", " ", title).strip()
    if JOB_ARTICLE.match(t):
        return False
    words = t.split()
    # Single Norwegian role compounds are common ("Regnskapskonsulent"); a long single word is a title,
    # a short one ("Karriere", "Kontakt") is a menu label and is rejected below or by length.
    if len(t) < 8 or (len(words) < 2 and not JOB_TITLE_HINT.search(t) and len(t) < 12):
        return False
    # Trailing punctuation ("Åpen søknad.") must not smuggle a no-vacancy notice past the rule.
    bare = re.sub(r"[\s.!?…:–-]+$", "", t)
    if JOB_MENU.match(t) or MENU_LABEL.match(t) or JOB_NOT_A_POSTING.match(t) or JOB_NOT_A_POSTING.match(bare):
        return False
    if JOB_CALL_TO_ACTION.match(t):
        return False
    return True


# A group careers page spans the whole group, so a card must name this register's country before its vacancy is
# attributed to a Norwegian company. Foreign group units are read as another employer, not this one.
NORWAY_MARKER = re.compile(r"\b(norge|norway|norsk)\b", re.I)
FOREIGN_MARKER = re.compile(
    r"\b(sverige|sweden|danmark|denmark|suomi|finland|asia|united kingdom|ireland|poland|polska|tyskland|"
    r"germany|nederland|netherlands|usa|united states|canada|brasil|brazil|india|singapore|malaysia|thailand|"
    r"bangladesh|pakistan|myanmar|hungary|ungarn|romania|estonia|latvia|lithuania|serbia|bulgaria|greece|spain|"
    r"italy|france|belgium|austria|switzerland|japan|china|korea|taiwan|vietnam|turkey|ukraine|czech|slovakia|"
    r"slovenia|croatia|portugal|mexico|chile|colombia|peru|argentina|south africa)\b",
    re.I,
)


def _employer_label(a: Any) -> str:
    """The hiring company a group careers card names, when the card marks it ("Telenor Norge")."""
    node = a.find(class_=re.compile(r"(compan|employer|organi[sz]ation)", re.I))
    return re.sub(r"\s+", " ", node.get_text(" ")).strip() if node is not None else ""


def jobs_from_html(page: Page, site: str, norway_only: bool = False) -> List[Dict[str, Any]]:
    """Postings from a careers/vacancies listing page: a human title and a same-site or known-ATS posting URL."""
    out: List[Dict[str, Any]] = []
    seen = set()
    today = datetime.now(timezone.utc).date()
    page_key = page.url.rstrip("/").lower()
    for a in page.soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(page.url, href.split("#")[0])
        local = same_site(url, site)
        if not local and not is_ats_posting(url):
            continue
        path = urlparse(url).path or "/"
        key = url.rstrip("/").lower()
        if key == page_key or key in seen or (local and NOTICE_PATH.search(path)):
            continue
        if _inside_navigation(a):
            continue
        heading = a.find(re.compile("^h[1-4]$")) or a.find_parent(re.compile("^h[1-4]$"))
        title = clean_job_title(_clean_title((heading or a).get_text(" ")))
        if not valid_job_title(title):
            continue
        label = _employer_label(a) if norway_only else ""
        if norway_only:
            card = label or re.sub(r"\s+", " ", a.get_text(" ")).strip()
            if not NORWAY_MARKER.search(card) or FOREIGN_MARKER.search(card):
                continue
        container = a.find_parent(["article", "li", "tr", "div"])
        # The title must name a role or a hiring action; careers-page culture/FAQ links never do.
        if not JOB_TITLE_HINT.search(title):
            continue
        if local and (PAGE_HINT.search(path) or NEWS_HINT.match(path + "/") or PRODUCT_PATH.search(path + "/")):
            continue
        seen.add(key)
        posted = None
        if container is not None:
            for node in container.find_all(["time"], limit=4):
                d = parse_date(node.get("datetime") or node.get_text(" "))
                if d and valid_publish_date(d, today):
                    posted = d.isoformat()
                    break
        out.append({
            "title": title,
            "url": url,
            "posted_at": posted,
            "found_on": page.url,
            "employer": label,
            "source": (f"posting by {label} on the group's shared careers page" if label else
                       "posting for this company's country on the group's shared careers page") if norway_only else
                      ("link on the company's careers page" if local else
                       "recruitment-service posting linked from the company's careers page"),
        })
        if len(out) >= MAX_JOBS:
            break
    return out


GROUP_JOBS_HINT = re.compile(r"(karriere|careers?|/jobs?/|ledige|vacanc|open-positions|vacant-positions|stillinger|jobbit)", re.I)


def find_group_careers_page(pages: List[Page], site: str, name: str) -> Optional[str]:
    """A careers page on the same company's other host (telenor.no -> telenor.com), not a third-party board.

    Large groups publish their vacancies on a shared group site rather than the subsidiary's own host. The link is
    only followed when the target host carries a distinctive token of this company's registered name, so a link to a
    recruitment agency or an unrelated group is never read.
    """
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            url = urljoin(page.url, href.split("#")[0]).split("?")[0]
            if same_site(url, site) or is_job_board_listing(url) or is_ats_posting(url):
                continue
            host = host_of(url)
            if not host or not domain_matches_name(host, name):
                continue
            if GROUP_JOBS_HINT.search(urlparse(url).path or "") or GROUP_JOBS_HINT.search(
                    re.sub(r"\s+", " ", a.get_text(" ")).strip()):
                return url
    return None


def jobs_from_jsonld(page: Page, site: str, today: date) -> List[Dict[str, Any]]:
    """schema.org JobPosting entries: the most reliable machine-readable posting a site can publish."""
    out: List[Dict[str, Any]] = []
    for s in page.soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            data = json.loads(s.string or s.get_text() or "null")
        except ValueError:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack += cur
                continue
            if not isinstance(cur, dict):
                continue
            kinds = cur.get("@type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(k == "JobPosting" for k in kinds):
                title = cur.get("title") or cur.get("name") or cur.get("headline")
                raw = cur.get("url") or cur.get("sameAs")
                d = parse_date(cur.get("datePosted"))
                if isinstance(title, str) and isinstance(raw, str):
                    url = urljoin(page.url, raw)
                    title = clean_job_title(_clean_title(title))
                    if (same_site(url, site) or is_ats_posting(url)) and valid_job_title(title) \
                            and JOB_TITLE_HINT.search(title):
                        out.append({
                            "title": title,
                            "url": url,
                            "posted_at": d.isoformat() if valid_publish_date(d, today) else None,
                            "found_on": page.url,
                            "source": "JSON-LD JobPosting",
                        })
            stack += [v for v in cur.values() if isinstance(v, (dict, list))]
    return out


def find_job_boards(pages: List[Page], limit: int = 2) -> List[str]:
    """Employer-scoped job-board pages linked from the site, most likely to render first.

    Finn's employer pages are server-rendered; Jobbnorge's search page is a JavaScript shell, so it is only tried
    as a fallback.
    """
    urls: List[str] = []
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            url = html.unescape(a["href"].strip()).split("#")[0]
            if is_job_board_listing(url) and url not in urls:
                urls.append(url)
    urls.sort(key=lambda u: 0 if "finn.no" in u else 1)
    return urls[:limit]


def jobs_from_board(page: Page, board_url: str, today: date) -> List[Dict[str, Any]]:
    """Postings shown on the employer-scoped board page the company's own careers page links to."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for a in page.soup.find_all("a", href=True):
        url = urljoin(page.url, html.unescape(a["href"].strip()).split("#")[0])
        if not is_job_board_posting(url):
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        heading = a.find(re.compile("^h[1-4]$")) or a.find_parent(re.compile("^h[1-4]$"))
        title = clean_job_title(_clean_title((heading or a).get_text(" ")))
        if not valid_job_title(title) or not JOB_TITLE_HINT.search(title):
            continue
        seen.add(key)
        posted = None
        container = a.find_parent(["article", "li", "tr", "div"])
        if container is not None:
            for node in container.find_all(["time"], limit=4):
                d = parse_date(node.get("datetime") or node.get_text(" "))
                if d and valid_publish_date(d, today):
                    posted = d.isoformat()
                    break
        out.append({"title": title, "url": url, "posted_at": posted, "found_on": board_url,
                    "source": "employer listing on a job board linked from the company's careers page"})
        if len(out) >= MAX_JOBS:
            break
    return out


def job_origin(source: str) -> str:
    """Where a posting is hosted, so nothing claims 'own site' for a job board.

    company_site             the posting is hosted on, or linked straight from, the verified company site
    linked_from_company_site a job board, recruiter or ATS that the company's own pages link to
    job_board_name_match     a Jobbnorge posting whose employer record has exactly this registered name
    group_site               a group careers page, only used when the card names this exact employer
    """
    s = (source or "").lower()
    if "exact employer name" in s:
        return "job_board_name_match"
    if "group's shared careers page" in s:
        return "group_site"
    if "link on the company's careers page" in s or "json-ld" in s:
        return "company_site"
    return "linked_from_company_site"


def employer_matches_label(label: str, name: str) -> bool:
    """A group careers card is attributed to this company only when it names exactly this employer."""
    return bool(label) and employer_key(label) == employer_key(name)


def publish_jobs(result: Dict[str, Any]) -> None:
    """Deduplicate the postings and rebuild their evidence items (the buyer summary reads these)."""
    result["jobs"] = dedupe_jobs(result["jobs"])
    for job in result["jobs"]:
        job.setdefault("origin", job_origin(job.get("source", "")))
    result["items"] = [it for it in result["items"] if not str(it.get("key", "")).startswith("job_item_")]
    for i, it in enumerate(result["jobs"], 1):
        when = it.get("posted_at") or "open / undated"
        read = (f"title, employer and date read from {it['found_on']}" if it.get("posted_at") else
                f"title and employer read from {it['found_on']}; the page shows no publish date")
        result["items"].append({
            "key": f"job_item_{i}",
            "value": f"{when} {it['title']}",
            "snippet": f"{when}: {it['title']}",
            "url": it["url"],
            "path": it["source"],
            "why": f"{it['source']}; {read}, nothing inferred.",
        })


def dedupe_jobs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One vacancy, one row. The same ad on two boards (FINN and Jobbnorge) is still one role; two identical
    titles on the same board are different vacancies (Vinmonopolet lists seven "Deltidsekspeditør" ads)."""
    seen, hosts_by_title, out = set(), {}, []
    for it in items:
        key = it["url"].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        title = re.sub(r"\s+", " ", it["title"]).strip().casefold()
        host = host_of(it["url"])
        hosts = hosts_by_title.setdefault(title, set())
        if hosts and host not in hosts:
            continue
        hosts.add(host)
        out.append(it)
    return out[:MAX_JOBS]


# --------------------------------------------------------------------------- 4d. SuccessFactors
# A SuccessFactors career site (jobs.yara.com) renders its landing page with categories only; its search URL,
# /search/?q=&locationsearch=<country>, is rendered on the server and lists the postings with location and date.
SF_POSTING = re.compile(r"^https?://(?P<host>[^/]+)/job/[^/?#]+/(?P<id>\d+)/?$", re.I)
SF_TTL = 900
_sf: Dict[str, Any] = {}


def is_successfactors(page: Page) -> bool:
    """A SuccessFactors career site marks itself with its j2w platform assets."""
    return bool(re.search(r"(/j2w/|successfactors)", page.text or "", re.I))


def successfactors_jobs(pages: List[Page], name: str, today: date, logs: List[str],
                        budget: Optional["WebBudget"] = None) -> List[Dict[str, Any]]:
    """Norwegian postings on the employer's own SuccessFactors career site, read from its country search.

    Only a careers host linked from the company's own pages and carrying the company's name is read (a career
    site is often a subdomain, jobs.yara.com), and only after its landing page has been fetched and identified
    as a SuccessFactors site, so an ordinary /job/ link elsewhere is never mistaken for a career site.
    """
    hosts: List[str] = []
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            url = urljoin(page.url, html.unescape(a["href"]).strip())
            host = host_of(url)
            if not host or host in hosts or host == host_of(page.url) or not domain_matches_name(host, name):
                continue
            label = re.sub(r"\s+", " ", a.get_text(" ")).strip()
            if JOB_HINT.search(urlparse(url).path or "") or JOB_HINT.search(label):
                hosts.append(host)
    out: List[Dict[str, Any]] = []
    for host in hosts[:2]:
        if len(out) >= MAX_JOBS:
            break
        landing = next((p for p in pages if host_of(p.url) == host), None)
        if landing is None and budget is not None and budget.used < budget.limit:
            landing = fetch(f"https://{host}/", budget, logs)
        if landing is None or not is_successfactors(landing):
            continue
        now = datetime.now(timezone.utc)
        cached = _sf.get(host)
        if isinstance(cached, dict) and (now - cached["at"]).total_seconds() < SF_TTL:
            out += cached["jobs"]
            continue
        search = f"https://{host}/search/?q=&locationsearch=Norway"
        found: List[Dict[str, Any]] = []
        if not robots_rules("https", host).allows(urlparse(search).path or "/"):
            logs.append(f"Website: {search} is disallowed by {host}/robots.txt; the SuccessFactors search was skipped.")
        else:
            try:
                resp = requests.get(search, headers=WEB_HEADERS, timeout=WEB_TIMEOUT)
                if resp.status_code != 200:
                    raise ValueError("no search page")
                soup = BeautifulSoup(resp.text, "html.parser")
                seen = set()
                for a in soup.find_all("a", href=True):
                    m = SF_POSTING.match(urljoin(search, html.unescape(a["href"]).strip()))
                    if not m or m.group("id") in seen:
                        continue
                    title = clean_job_title(_clean_title(a.get_text(" ")))
                    if not valid_job_title(title):
                        continue
                    row = a.find_parent("tr") or a.find_parent(["li", "article", "div"])
                    loc_node = row.find(class_=re.compile(r"(^|\s)(colLocation|jobLocation)(\s|$)", re.I)) if row else None
                    date_node = row.find(class_=re.compile(r"(^|\s)(colDate|jobDate)(\s|$)", re.I)) if row else None
                    place = re.sub(r"\s+", " ", loc_node.get_text(" ")).strip() if loc_node else ""
                    if place and not (_NORWAY.search(place) or re.search(r",\s*NO\b", place)):
                        continue
                    posted = parse_date(date_node.get_text(" ")) if date_node else None
                    seen.add(m.group("id"))
                    found.append({
                        "title": title,
                        "url": m.group(0),
                        "posted_at": posted.isoformat() if valid_publish_date(posted, today) else None,
                        "found_on": search,
                        "source": f"SuccessFactors career site of the employer, Norway search (location {place or 'Norway'})",
                    })
                    if len(found) >= MAX_JOBS:
                        break
                logs.append(f"Website: the SuccessFactors search at {host} listed {len(found)} Norwegian posting(s).")
            except (requests.RequestException, ValueError):
                logs.append(f"Website: the SuccessFactors search at {host} could not be read; its postings were skipped.")
        _sf[host] = {"at": now, "jobs": found}
        out += found
    return out[:MAX_JOBS]


# --------------------------------------------------------------------------- 4b. Jobbnorge
# Jobbnorge's own search page is a JavaScript shell: fetched as HTML it lists nothing. Their search page reads
# publicapi.jobbnorge.no/v3/jobs, a public JSON feed that carries employerID, employer name, title, link and
# publication date, so the same postings can be read without rendering JavaScript.
JOBNORGE_API = "https://publicapi.jobbnorge.no/v3/jobs?language=1"
JOBNORGE_TTL = 900                      # one feed request per 15 minutes, shared by every company in a run
_JOB_EMPLOYER_LINK = re.compile(r"jobbnorge\.no/(?:[a-z]{2}/)?(?:search|ledige-stillinger)[^\"'\s<>]*?[?&]employer=(\d+)", re.I)
_jobbnorge: Dict[str, Any] = {"at": None, "jobs": []}
LEGAL_FORM_WORDS = ("asa", "as", "ans", "da", "sa", "ks", "nuf", "enk", "iks", "sf", "stiftelse", "stiftelsen", "ab", "oy")


def employer_key(text: str) -> str:
    """Fold a registered name and a Jobbnorge employer name to the same key, dropping the legal form."""
    folded = text.casefold().replace("\u00e6", "ae").replace("\u00f8", "o").replace("\u00e5", "a")
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^a-z0-9& ]+", " ", folded)
    words = [w for w in folded.split() if w not in LEGAL_FORM_WORDS]
    return " ".join(words).strip()


def jobbnorge_feed(logs: List[str]) -> List[Dict[str, Any]]:
    """All open Jobbnorge postings, cached per process. A failed read is cached too, so a run never hammers it."""
    now = datetime.now(timezone.utc)
    at = _jobbnorge.get("at")
    if isinstance(at, datetime) and (now - at).total_seconds() < JOBNORGE_TTL:
        return _jobbnorge["jobs"]
    jobs: List[Dict[str, Any]] = []
    try:
        resp = requests.get(JOBNORGE_API, headers=WEB_HEADERS, timeout=WEB_TIMEOUT)
        data = resp.json() if resp.status_code == 200 else None
        found = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(found, list):
            raise ValueError("no job list")
        jobs = [j for j in found if isinstance(j, dict)]
        logs.append(f"Website: the Jobbnorge job API listed {len(jobs)} open posting(s).")
    except (requests.RequestException, ValueError):
        logs.append("Website: the Jobbnorge job API could not be read; Jobbnorge postings were skipped.")
    _jobbnorge.update(at=now, jobs=jobs)
    return jobs


def jobbnorge_employer_ids(pages: List[Page]) -> List[str]:
    ids: List[str] = []
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            m = _JOB_EMPLOYER_LINK.search(html.unescape(a["href"]))
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


# --------------------------------------------------------------------------- 4c. Workday
# Large employers publish vacancies only in their own Workday tenant (equinor.wd3.myworkdayjobs.com/EQNR). The
# careers page is a JavaScript shell, but the tenant's public job feed - the JSON its own page calls - lists the
# postings with title, location and posting date, so the same vacancies can be read without a browser.
WORKDAY_URL = re.compile(
    r"^https://(?P<tenant>[a-z0-9-]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com/"
    r"(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[A-Za-z0-9_-]+)",
    re.I,
)
WORKDAY_TTL = 900                      # one feed request per tenant per 15 minutes, shared by a whole run
_NORWAY = re.compile(r"\b(norway|norge|noreg)\b", re.I)
_workday: Dict[str, Any] = {}


def workday_sites(pages: List[Page], name: str) -> List[Dict[str, str]]:
    """Workday tenants this company links from its own site, kept only when the tenant host carries its name.

    The tenant subdomain is the employer (equinor.wd3..., norskhydro.wd3...), so a link to another company's
    tenant - the parent group's or an agency's - is never read for this company.
    """
    out: List[Dict[str, str]] = []
    for page in pages:
        for a in page.soup.find_all("a", href=True):
            m = WORKDAY_URL.match(html.unescape(a["href"]).strip())
            if not m:
                continue
            host = f"{m.group('tenant').lower()}.{m.group('wd').lower()}.myworkdayjobs.com"
            if not domain_matches_name(host, name):
                continue
            site = {"host": host, "tenant": m.group("tenant").lower(), "site": m.group("site"),
                    "linked_from": page.url}
            if not any((s["host"], s["site"]) == (site["host"], site["site"]) for s in out):
                out.append(site)
    return out[:2]


def workday_feed(site: Dict[str, str], logs: List[str]) -> List[Dict[str, Any]]:
    """Open postings the tenant lists, cached per process. A failed read is cached too, so a run never hammers it."""
    key = f"{site['host']}/{site['site']}"
    now = datetime.now(timezone.utc)
    cached = _workday.get(key)
    if isinstance(cached, dict) and (now - cached["at"]).total_seconds() < WORKDAY_TTL:
        return cached["jobs"]
    url = f"https://{site['host']}/wday/cxs/{site['tenant']}/{site['site']}/jobs"
    jobs: List[Dict[str, Any]] = []
    if not robots_rules("https", site["host"]).allows(urlparse(url).path or "/"):
        logs.append(f"Website: {url} is disallowed by {site['host']}/robots.txt; Workday postings were skipped.")
    else:
        try:
            resp = requests.post(
                url,
                json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
                headers={**WEB_HEADERS, "Accept": "application/json", "Content-Type": "application/json"},
                timeout=WEB_TIMEOUT,
            )
            data = resp.json() if resp.status_code == 200 else None
            found = data.get("jobPostings") if isinstance(data, dict) else None
            if not isinstance(found, list):
                raise ValueError("no job list")
            jobs = [j for j in found if isinstance(j, dict)]
            logs.append(f"Website: the Workday job feed at {site['host']} listed {len(jobs)} posting(s).")
        except (requests.RequestException, ValueError):
            logs.append(f"Website: the Workday job feed at {site['host']} could not be read; its postings were skipped.")
    _workday[key] = {"at": now, "jobs": jobs}
    return jobs


def workday_detail(site: Dict[str, str], external_path: str) -> Optional[Dict[str, Any]]:
    """The tenant's own record for one posting: its country, location, publish date and canonical URL."""
    url = f"https://{site['host']}/wday/cxs/{site['tenant']}/{site['site']}{external_path}"
    if not robots_rules("https", site["host"]).allows(urlparse(url).path or "/"):
        return None
    try:
        resp = requests.get(url, headers={**WEB_HEADERS, "Accept": "application/json"}, timeout=WEB_TIMEOUT)
        data = resp.json() if resp.status_code == 200 else None
        info = data.get("jobPostingInfo") if isinstance(data, dict) else None
        return info if isinstance(info, dict) else None
    except (requests.RequestException, ValueError):
        return None


def workday_jobs(name: str, sites: List[Dict[str, str]], today: date, logs: List[str]) -> List[Dict[str, Any]]:
    """Norwegian vacancies in the employer's own Workday tenant, each dated from the tenant's own record."""
    out: List[Dict[str, Any]] = []
    for site in sites:
        feed = workday_feed(site, logs)
        if not feed:
            continue
        listed = sum(1 for j in feed if _NORWAY.search(str(j.get("locationsText") or "")))
        details = 0
        for job in feed:
            if len(out) >= MAX_JOBS:
                break
            if not _NORWAY.search(str(job.get("locationsText") or "")):
                continue
            title = clean_job_title(_clean_title(str(job.get("title") or "")))
            path = job.get("externalPath")
            if not isinstance(path, str) or not path.startswith("/job/") or not valid_job_title(title):
                continue
            # The posting's own record is the proof: its country must be Norway, its start date is the publish date.
            info = workday_detail(site, path)
            details += 1
            country = info.get("country") if isinstance(info, dict) else None
            if isinstance(country, dict) and str(country.get("descriptor", "")).casefold() not in ("", "norway", "norge"):
                continue
            posted = parse_date(info.get("startDate")) if isinstance(info, dict) else None
            link = info.get("externalUrl") if isinstance(info, dict) and isinstance(info.get("externalUrl"), str) \
                else f"https://{site['host']}/{site['site']}{path}"
            place = (info.get("location") if isinstance(info, dict) else None) or job.get("locationsText") or "Norway"
            out.append({
                "title": title,
                "url": link,
                "posted_at": posted.isoformat() if valid_publish_date(posted, today) else None,
                "found_on": f"the employer's Workday tenant {site['host']}/{site['site']} (linked from {site['linked_from']})",
                "source": f"Workday public job feed, location {place}",
            })
        if listed and not out:
            logs.append(f"Website: Workday listed {listed} posting(s) in Norway for this employer but none had a usable role title.")
        if details:
            logs.append(f"Website: {details} Workday posting record(s) read from {site['host']}.")
    return out


def jobbnorge_jobs(name: str, employer_ids: List[str], today: date, logs: List[str]) -> List[Dict[str, Any]]:
    """Postings the employer itself published on Jobbnorge, matched by employer id or exact employer name."""
    wanted = employer_key(name)
    wanted_tokens = set(wanted.split())
    # A registered name and a board employer name are often the same words in another order
    # ("NORGES TEKNISK-... UNIVERSITET NTNU" vs "NTNU - Norges teknisk-... universitet").
    use_name = not employer_ids and len(wanted) >= 8 and len(wanted_tokens) >= 2
    ids = set(employer_ids)
    matched = 0
    out: List[Dict[str, Any]] = []
    for job in jobbnorge_feed(logs):
        employer = job.get("employer") if isinstance(job.get("employer"), str) else ""
        by_id = str(job.get("employerID")) in ids
        by_name = use_name and set(employer_key(employer).split()) == wanted_tokens
        if not (by_id or by_name):
            continue
        matched += 1
        title = clean_job_title(_clean_title(job.get("title") or ""))
        link = job.get("link") if isinstance(job.get("link"), str) else ""
        # The board's own employer record is the match, so a real title is enough; menu labels and
        # no-vacancy notices are still rejected by valid_job_title.
        if not valid_job_title(title) or not is_job_board_posting(link):
            continue
        posted = parse_date(job.get("publicationDate"))
        # A board keeps old notices online; only a posting published within the last year is published here.
        if posted and (today - posted).days > 365:
            continue
        out.append({
            "title": title,
            "url": link,
            "posted_at": posted.isoformat() if valid_publish_date(posted, today) else None,
            "found_on": f"{JOBNORGE_API} (employer {employer})",
            "source": "Jobbnorge public job API, employer matched " + ("by the employer link on the company site" if by_id else "by exact employer name"),
        })
        if len(out) >= MAX_JOBS:
            break
    if matched and not out:
        logs.append(f"Website: Jobbnorge showed {matched} posting(s) for this employer but none had a usable role title.")
    return out


# --------------------------------------------------------------------------- orchestration
def enrich(number: str, name: str, registry_website: Any, sess: Any, throttle: Callable[[], None],
           logs: List[str], today: Optional[date] = None) -> Dict[str, Any]:
    """Returns {'website': {...}, 'social_links': [...], 'news': [...], 'jobs': [...], 'items': [...]}."""
    today = today or datetime.now(timezone.utc).date()
    url = normalize_url(registry_website)
    result: Dict[str, Any] = {"website": {"registry_url": registry_website if isinstance(registry_website, str) else None,
                                          "url": None, "status": "no_website", "verified": False, "verified_by": None,
                                          "pages_checked": []},
                              "social_links": [], "news": [], "jobs": [], "items": []}
    site = result["website"]
    # Postings the employer published on Jobbnorge are readable without the company's own site, and the
    # employer match (exact name) is the proof, so they are collected before any website work.
    result["jobs"] = jobbnorge_jobs(name, [], today, logs)
    if not url:
        logs.append("Website: the registry lists no usable website; social links and news are not searched.")
        publish_jobs(result)
        return result
    budget = WebBudget(sess, throttle)
    home = fetch(url, budget, logs)
    if home is None and url.startswith("https://") and budget.used < budget.limit:
        home = fetch("http://" + url[len("https://"):], budget, logs)
    if home is None:
        site.update(status="unreachable", url=url)
        logs.append(f"Website: {url} could not be read, so ownership could not be verified; social links and news from the site are left empty.")
        publish_jobs(result)
        return result
    site["pages_checked"].append(home.url)
    site_url = home.url
    host = host_of(site_url)
    how = verify_ownership(home, number, name)
    verified_page = home if how else None
    extra: List[Page] = []
    if not how:
        for cand in candidate_pages(home):
            page = fetch(cand, budget, logs)
            if page is None:
                continue
            site["pages_checked"].append(page.url)
            extra.append(page)
            how = verify_ownership(page, number, name)
            if how:
                verified_page = page
                break
    if not how:
        site.update(status="not_verified", url=url, reason=(
            f"{host} shows neither organisation number {number} nor the exact name '{name}' on the home page or its contact/about/privacy pages; "
            "it is treated as a parent-group or brand site, so no social links, news or jobs were taken from it."))
        logs.append("Website: " + site["reason"])
        publish_jobs(result)
        return result
    site.update(status="verified", verified=True, verified_by=how, url=site_url,
                verified_on=verified_page.url if verified_page else site_url)
    logs.append(f"Website: {host} verified as this company's own site by {how.replace('_', ' ')} on {site['verified_on']}.")
    result["items"].append({"key": "website", "value": site_url, "snippet": f"Website {site_url} shows this company's {how.replace('_', ' ')}.",
                            "url": site["verified_on"], "path": "page text / JSON-LD",
                            "why": f"Registry lists '{registry_website}'; the page at {site['verified_on']} contains this company's "
                                   f"{'organisation number ' + number if how == 'organisation_number' else 'exact registered name ' + repr(name)}, so the site is its own."})

    pages = [home] + extra
    social, rejected = extract_social(pages, name, host)
    for s in social:
        result["social_links"].append(s)
        result["items"].append({"key": f"social_{s['platform']}", "value": s["url"], "snippet": f"{s['platform']}: {s['url']}",
                                "url": s["found_on"], "path": "a[href] / JSON-LD sameAs",
                                "why": f"Link found on the verified company site; {s['matched']} ('{s['handle']}')."})
    if rejected:
        logs.append(f"Website: {len(rejected)} social link(s) discarded (group, agency, theme, share or personal): "
                    + "; ".join(rejected[:6]) + ("..." if len(rejected) > 6 else "") + ".")

    sitemap_cache: List[str] = []
    sitemap_done = False

    def sitemap_pages() -> List[str]:
        nonlocal sitemap_done, sitemap_cache
        if not sitemap_done:
            sitemap_cache = sitemap_urls(home, budget, logs)
            sitemap_done = True
        return sitemap_cache

    news: List[Dict[str, Any]] = []
    feed_url = find_feed(home)
    if feed_url:
        feed = fetch(feed_url, budget, logs)
        if feed:
            news += news_from_feed(feed, site_url, today)
    if len(news) < 3:
        news_url = find_news_page(home)
        if not news_url:
            for cand in sitemap_pages():
                if same_site(cand, site_url) and NEWS_HINT.match(urlparse(cand).path + "/"):
                    news_url = cand
                    break
        if news_url:
            news_page = fetch(news_url, budget, logs)
            if news_page:
                news += news_from_html(news_page, site_url, today)
    news += news_from_html(home, site_url, today)
    news = dedupe_news(news, today)
    result["news"] = news
    for i, it in enumerate(news, 1):
        result["items"].append({"key": f"news_item_{i}", "value": f"{it['published_at']} {it['title']}", "snippet": f"{it['published_at']}: {it['title']}",
                                "url": it["url"], "path": it["source"],
                                "why": f"Dated post on the verified company site; publish date {it['published_at']} from {it['source']} "
                                       f"(modified/updated dates are never used); found on {it['found_on']}."})

    jobs: List[Dict[str, Any]] = list(result["jobs"])
    jobs_url = find_jobs_page(pages)
    if not jobs_url:
        for cand in sitemap_pages():
            if same_site(cand, site_url) and JOB_HINT.search(urlparse(cand).path or ""):
                jobs_url = cand
                break
    if not jobs_url:
        # Common careers paths, tried only after the site itself offered no link (still the company's own host).
        for guess in ("karriere", "karriere-i-virksomheten", "jobb", "ledige-stillinger", "careers"):
            if budget.used >= budget.limit:
                break
            cand = urljoin(site_url.rstrip("/") + "/", guess)
            probe = fetch(cand, budget, logs)
            if probe is not None and JOB_HINT.search(urlparse(probe.url).path or ""):
                jobs_url = probe.url
                break
    jobs_page = None
    if jobs_url and budget.used < budget.limit:
        jobs_page = fetch(jobs_url, budget, logs)
        if jobs_page:
            jobs += jobs_from_html(jobs_page, site_url)
            jobs += jobs_from_jsonld(jobs_page, site_url, today)
    for board_url in find_job_boards(pages + ([jobs_page] if jobs_page else [])):
        if budget.used >= budget.limit or len(jobs) >= 3:
            break
        board = fetch(board_url, budget, logs)
        if board is None:
            continue
        found = jobs_from_board(board, board_url, today)
        if found:
            jobs += found
            break
    jobs += jobs_from_jsonld(home, site_url, today)
    # A group that publishes vacancies on a shared careers site (telenor.no -> telenor.com) keeps the company's own
    # host free of postings. Read that page only when its host carries the company's name, and only postings that
    # live on that same host, so nothing from an agency or a sister brand slips in.
    group_page = None
    if sum(1 for j in jobs if j.get("url")) < 3:
        group_url = find_group_careers_page(([jobs_page] if jobs_page else []) + pages, site_url, name)
        if group_url and budget.used < budget.limit:
            group_page = fetch(group_url, budget, logs)
            if group_page:
                listed = jobs_from_html(group_page, group_page.url, norway_only=True)
                found = [j for j in listed if employer_matches_label(j.get("employer", ""), name)]
                jobs += found
                logs.append(f"Website: the company's careers page sent us to {host_of(group_page.url)}; "
                            f"{len(found)} of {len(listed)} Norwegian posting(s) there name exactly this employer "
                            "(a sister or subsidiary unit such as 'Telenor Norge' is not attributed to the parent).")
    # A SuccessFactors career site linked from the company lists its postings only on its own country search.
    jobs += successfactors_jobs(pages + ([jobs_page] if jobs_page else []) + ([group_page] if group_page else []),
                                name, today, logs, budget)
    # Jobbnorge postings are published by the employer on a job board, not on its own site. Read the board's
    # public JSON feed rather than the JavaScript page, matching this employer by id or by exact employer name.
    ids = jobbnorge_employer_ids(pages + ([jobs_page] if jobs_page else []))
    if ids:
        # The employer link on the site is stronger proof than a name match, so it replaces those entries.
        jobs = [j for j in jobs if "exact employer name" not in j["source"]]
    jobs += jobbnorge_jobs(name, ids, today, logs)
    # Employers that run their own Workday tenant link it from their careers page. The page itself is a JavaScript
    # shell, so the tenant's public job feed is read instead, and only when the tenant host carries this name.
    workday = workday_sites(pages + ([jobs_page] if jobs_page else []), name)
    if workday:
        jobs += workday_jobs(name, workday, today, logs)
    result["jobs"] = jobs
    publish_jobs(result)
    jobs = result["jobs"]

    logs.append(
        f"Website: {len(social)} social account(s), {len(news)} dated news item(s), "
        f"{len(jobs)} job posting(s); {budget.used} website request(s)."
    )
    return result