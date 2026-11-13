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
        if urlparse(current).scheme not in ("http", "https") or not public_host(host):
            logs.append(f"Website: refused to fetch {current} (not a public http(s) host).")
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
JOB_NOT_A_POSTING = re.compile(r"^(\u00e5pen s\u00f8knad|apen soknad|open application|send (us )?(an )?application|contact us|kontakt oss)$", re.I)
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


def valid_job_title(title: str) -> bool:
    t = re.sub(r"\s+", " ", title).strip()
    if len(t) < 8 or (len(t.split()) < 2 and not JOB_TITLE_HINT.search(t)):
        return False
    if JOB_MENU.match(t) or MENU_LABEL.match(t) or JOB_NOT_A_POSTING.match(t):
        return False
    return True


def jobs_from_html(page: Page, site: str) -> List[Dict[str, Any]]:
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
        title = _clean_title((heading or a).get_text(" "))
        if not valid_job_title(title):
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
            "source": "link on the company's careers page" if local else "recruitment-service posting linked from the company's careers page",
        })
        if len(out) >= MAX_JOBS:
            break
    return out


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
                    title = _clean_title(title)
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
        title = _clean_title((heading or a).get_text(" "))
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


def dedupe_jobs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        key = it["url"].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out[:MAX_JOBS]


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
    if not url:
        logs.append("Website: the registry lists no usable website; social links, news and jobs are not searched.")
        return result
    budget = WebBudget(sess, throttle)
    home = fetch(url, budget, logs)
    if home is None and url.startswith("https://") and budget.used < budget.limit:
        home = fetch("http://" + url[len("https://"):], budget, logs)
    if home is None:
        site.update(status="unreachable", url=url)
        logs.append(f"Website: {url} could not be read, so ownership could not be verified; social links, news and jobs left empty.")
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

    jobs: List[Dict[str, Any]] = []
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
    jobs = dedupe_jobs(jobs)
    result["jobs"] = jobs
    for i, it in enumerate(jobs, 1):
        when = it.get("posted_at") or "open / undated"
        result["items"].append({
            "key": f"job_item_{i}",
            "value": f"{when} {it['title']}",
            "snippet": f"{when}: {it['title']}",
            "url": it["url"],
            "path": it["source"],
            "why": (
                f"Job posting linked from the verified company site; "
                f"title and URL taken from the company's own page ({it['found_on']})."
            ),
        })

    logs.append(
        f"Website: {len(social)} social account(s), {len(news)} dated news item(s), "
        f"{len(jobs)} job posting(s); {budget.used} website request(s)."
    )
    return result