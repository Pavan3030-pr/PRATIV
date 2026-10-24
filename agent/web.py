"""Website enrichment for the Signalpost agent: website ownership check, social links, news.

Rules (each one answers an audit finding):
  1. The registry's website is only used for social links and news after the site itself shows this
     company's organisation number or its exact registered name. A parent-group or brand site fails
     that check, is reported as not verified, and nothing is taken from it.
  2. A social account is published only if its handle matches the company (its legal name or its own
     verified domain). Footer links of the parent group, the web agency, the website theme, share
     buttons and personal profiles never match and are discarded.
  3. A news item must be a real post: its own page on the same site, a human title (not a menu label
     like "See more news"), not a product/service page, and a publish date taken from a publish
     field (time[datetime], datePublished, RSS pubDate, Atom published). "modified", "updated",
     dateModified, lastBuildDate and Atom <updated> are never used as a publish date.
Everything else stays empty with a stated reason; nothing is guessed.
"""
from __future__ import annotations

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

LEGAL_FORMS = {"as", "asa", "ans", "da", "ba", "sa", "ks", "nuf", "enk", "iks", "sf", "stift", "ltd", "ab", "oy", "gmbh"}
PAGE_HINT = re.compile(r"(kontakt|contact|om-oss|omoss|about|personvern|privacy|vilkar|vilk%c3%a5r|terms|betingelser|impressum|cookie|handelsbetingelser)", re.I)
NEWS_HINT = re.compile(r"^/(nyheter|nyhet|nytt|news|aktuelt|aktuelle-saker|blogg|blog|presse|pressemeldinger|press|artikler|nyhetsarkiv|siste-nytt)/?$", re.I)
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


def verify_ownership(page: Page, number: str, name: str) -> Optional[str]:
    text = _page_text(page)
    if org_number_pattern(number).search(text):
        return "organisation_number"
    pat = name_pattern(name)
    if pat and pat.search(text):
        return "exact_legal_name"
    return None


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
def name_keys(name: str, site_host: str) -> Dict[str, str]:
    """Keys a social handle may equal. Deliberately narrow: legal name (with/without legal form) or the verified domain."""
    tokens = re.findall(r"\w+", name.casefold())
    core_tokens = tokens[:]
    while core_tokens and core_tokens[-1] in LEGAL_FORMS:
        core_tokens.pop()
    keys = {}
    if core_tokens:
        keys[fold("".join(core_tokens))] = "company name"
    keys[fold("".join(tokens))] = "company name"
    label = site_host.split(".")[-2] if site_host.count(".") >= 1 else site_host
    if fold(label):
        keys.setdefault(fold(label), "own verified website domain")
    keys.pop("", None)
    return keys


def handle_variants(handle: str) -> List[str]:
    h = handle.lstrip("@")
    h = re.sub(r"[-_]?\d{4,}$", "", h)        # LinkedIn slugs end in numeric ids
    variants = {fold(h)}
    for suffix in ("official", "as", "asa"):
        f = fold(h)
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
                    rejected.append(f"{platform}:{handle} (handle does not match this company)")
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


# --------------------------------------------------------------------------- orchestration
def enrich(number: str, name: str, registry_website: Any, sess: Any, throttle: Callable[[], None],
           logs: List[str], today: Optional[date] = None) -> Dict[str, Any]:
    """Returns {'website': {...}, 'social_links': [...], 'news': [...], 'items': [...evidence rows...]}."""
    today = today or datetime.now(timezone.utc).date()
    url = normalize_url(registry_website)
    result: Dict[str, Any] = {"website": {"registry_url": registry_website if isinstance(registry_website, str) else None,
                                          "url": None, "status": "no_website", "verified": False, "verified_by": None,
                                          "pages_checked": []},
                              "social_links": [], "news": [], "items": []}
    site = result["website"]
    if not url:
        logs.append("Website: the registry lists no usable website; social links and news are not searched.")
        return result
    budget = WebBudget(sess, throttle)
    home = fetch(url, budget, logs)
    if home is None and url.startswith("https://") and budget.used < budget.limit:
        home = fetch("http://" + url[len("https://"):], budget, logs)
    if home is None:
        site.update(status="unreachable", url=url)
        logs.append(f"Website: {url} could not be read, so ownership could not be verified; social links and news left empty.")
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

    news: List[Dict[str, Any]] = []
    news_page = None
    feed_url = find_feed(home)
    if feed_url:
        feed = fetch(feed_url, budget, logs)
        if feed:
            news += news_from_feed(feed, site_url, today)
    if len(news) < 3:
        news_url = find_news_page(home)
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
    logs.append(f"Website: {len(social)} social account(s) and {len(news)} dated news item(s) published; {budget.used} website request(s).")
    return result
