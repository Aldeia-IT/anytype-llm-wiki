"""wiki/fetch.py — URL/file fetching with SSRF protections (AC#4, AC#17).

Adapts the master spec's reference SSRF implementation (§SSRF protections).
URL fetches and every redirect hop are validated against the RESOLVED IP
(categorical private/loopback/link-local/reserved check — addendum item 4),
NOT textual host matching. HTML is converted to markdown via ``markdownify``.

All rejections surface to the caller as a ``[DATA ERROR] ssrf_blocked: ...``
string; the function never raises for an unsafe URL — it returns the marker
string so the ingest pipeline can short-circuit cleanly.
"""

import ipaddress
import os
import re
import socket
from pathlib import Path

import httpx

from .. import __version__
from . import config

# Descriptive User-Agent sent on every fetch hop. Wikimedia's bot policy (and
# other sites) reject the default ``python-httpx/x.y`` with a 403.
USER_AGENT = (
    f"anytype-llm-wiki/{__version__} (+https://github.com/Aldeia-IT/anytype-llm-wiki)"
)

_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_ALLOWED_PORTS = {None, 80, 443}

# Defense-in-depth blocklist combined with the categorical is_* checks below.
_BLOCKED_NETS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

AddressLike = ipaddress.IPv4Address | ipaddress.IPv6Address

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 5


class SsrfBlocked(Exception):
    """Raised internally when a URL or redirect target is unsafe."""


def _allowed_ports() -> set:
    return _DEFAULT_ALLOWED_PORTS | set(config.fetch_extra_ports())


def _max_bytes() -> int:
    raw = os.environ.get("WIKI_FETCH_MAX_BYTES")
    if not raw:
        return _DEFAULT_MAX_BYTES
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_MAX_BYTES


def _resolve_all(host: str) -> list[AddressLike]:
    """Return every A/AAAA address the OS resolver yields for ``host``.

    getaddrinfo (not gethostbyname) so BOTH IPv4 and IPv6 are checked; a single
    unsafe address rejects the fetch (defeats multi-A-record resolver attacks).
    """
    results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)  # nosec B312 — resolved IPs are categorically validated by _is_blocked
    addrs: list[AddressLike] = []
    for _family, _type, _proto, _canon, sockaddr in results:
        addrs.append(ipaddress.ip_address(sockaddr[0]))
    return addrs


def _is_blocked(addr: AddressLike) -> bool:
    # Normalize IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) so IPv4 rules engage.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if any(addr in net for net in _BLOCKED_NETS):
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _assert_url_safe(url: httpx.URL) -> None:
    """Raise SsrfBlocked if ``url`` is unsafe (resolved-IP categorical check)."""
    if url.scheme not in _ALLOWED_SCHEMES:
        raise SsrfBlocked(f"scheme not allowed: {url.scheme}")
    if url.userinfo:
        raise SsrfBlocked("url userinfo not allowed")
    if url.port not in _allowed_ports():
        raise SsrfBlocked(f"port not allowed: {url.port}")
    if not url.host:
        raise SsrfBlocked("url has no host")
    try:
        addrs = _resolve_all(url.host)
    except socket.gaierror as exc:
        # An unresolvable host (incl. numeric-encoded forms the resolver rejects)
        # is treated as blocked rather than crashing — addendum item 4.
        raise SsrfBlocked(f"host did not resolve: {url.host} ({exc})") from exc
    if not addrs:
        raise SsrfBlocked(f"host did not resolve: {url.host}")
    for addr in addrs:
        if _is_blocked(addr):
            raise SsrfBlocked(
                f"refusing to fetch private/reserved address: {url.host} -> {addr}"
            )


# Elements that never carry article content: removed before the root is chosen.
_BOILERPLATE_TAGS = (
    "script", "style", "noscript", "template", "svg", "iframe", "nav", "aside",
)
# Page chrome only outside the root: an <article> carries its own <header> (the
# post title) and <footer> (tags, byline) in the standard WordPress layout.
_CHROME_OUTSIDE_ROOT_TAGS = ("header", "footer")
# A <form> is removed unless it wraps the root or holds this share of the body
# text (ASP.NET WebForms wraps the whole page in <form id="aspnetForm">).
_FORM_KEEP_TEXT_SHARE = 0.5
_BOILERPLATE_ROLES = ("navigation", "banner", "contentinfo", "search")
_MAIN_ROOT_SELECTORS = ("main", "article", "[role=main]")
# The chosen root must hold at least this share of the stripped body's text;
# otherwise it is a teaser (or the article sits elsewhere) and the body is used.
_ROOT_MIN_TEXT_SHARE = 0.25

# AC9 usable-content gate thresholds and markers.
_MIN_VISIBLE_CHARS = 300
# Interstitial (bot-challenge) markers decide only on a page this short, so an
# article that merely mentions one is kept.
_CHALLENGE_MAX_VISIBLE_CHARS = 2000
_CHALLENGE_MARKERS = (
    "cf-chl",
    "just a moment...",
    "checking your browser",
    "attention required",
)
# Captcha widgets also sit in ordinary login, comment and contact forms (a group
# site's home page with ~1,500 chars of text carried g-recaptcha), so they mark a
# challenge only on a page with no usable text of its own.
_CAPTCHA_MARKERS = ("g-recaptcha", "h-captcha", "cf-turnstile")
_JS_MOUNT_IDS = re.compile(r"^(root|app|__next)$")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_BARE_URL_RE = re.compile(r"<?https?://\S+>?")
_MD_SYNTAX_RE = re.compile(r"[#*_>`|~=\[\]-]+")


def _visible_text(node) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _is_inside(el, ancestor) -> bool:
    """True when ``el`` is a descendant of ``ancestor`` (False if either is None)."""
    if el is None or ancestor is None:
        return False
    return any(parent is ancestor for parent in el.parents)


def strip_boilerplate(html: str) -> str:
    """Return the HTML of a page's main content, with the site chrome removed.

    Removes ``script, style, noscript, template, svg, iframe, nav, aside``, ARIA
    ``role=navigation|banner|contentinfo|search`` and ``aria-hidden=true``
    elements, then picks the first of ``main``, ``article``, ``[role=main]`` as
    the root (else ``body``). ``header`` and ``footer`` are removed only outside
    the root (an article's own header holds its title). A ``form`` is removed
    unless it wraps the root or holds at least half of the body text (a page
    wrapped in one form, as ASP.NET WebForms does); search, contact and login
    forms go. Safety fallback: when the chosen root's visible text is under 25 %
    of the stripped body's text (a teaser ``<article>``, or a page that keeps
    its article outside the landmark), the stripped ``body`` is returned
    instead. No per-site rules.

    Known limitation: the share is measured against the body AFTER all
    removals, so an article a site places inside a page-level ``<header>`` (or
    ``<nav>``, ``<aside>``…) outside any landmark is removed with it and is not
    recovered by the fallback.

    :param html: the raw HTML document (or fragment).
    :returns: the HTML string of the chosen root, ready for markdownify.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for el in soup(list(_BOILERPLATE_TAGS)):
        el.decompose()
    for el in soup.select(
        ",".join(f"[role={role}]" for role in _BOILERPLATE_ROLES) + ",[aria-hidden=true]"
    ):
        el.decompose()

    body = soup.body or soup
    root = None
    for selector in _MAIN_ROOT_SELECTORS:
        root = soup.select_one(selector)
        if root is not None:
            break

    for el in soup(list(_CHROME_OUTSIDE_ROOT_TAGS)):
        if el.decomposed or _is_inside(el, root) or _is_inside(root, el) or el is root:
            continue
        el.decompose()

    body_len = len(_visible_text(body))
    for form in soup("form"):
        if form.decomposed or form is root or _is_inside(root, form):
            continue
        if body_len and len(_visible_text(form)) >= _FORM_KEEP_TEXT_SHARE * body_len:
            continue
        form.decompose()

    if root is None:
        return str(body)
    body_len = len(_visible_text(body))
    if body_len and len(_visible_text(root)) < _ROOT_MIN_TEXT_SHARE * body_len:
        return str(body)
    return str(root)


def _to_markdown(text: str, content_type: str, *, strip: bool = True) -> str:
    """Convert HTML to markdown; pass plain text/markdown through unchanged.

    HTML is reduced to its main content first (``strip_boilerplate``) unless
    ``strip`` is False (the dry-run harness measures the unstripped size).
    """
    if "html" in (content_type or "").lower() or _looks_like_html(text):
        from markdownify import markdownify as _md

        html = strip_boilerplate(text) if strip else text
        md = _md(html, heading_style="ATX")
        return re.sub(r"\n{3,}", "\n\n", md).strip()
    return text


def markdown_visible_text(markdown: str) -> str:
    """Return the reader-visible text of ``markdown``.

    Image references and link targets are dropped (an image keeps its alt text, a
    link its label), bare URLs and markdown syntax characters are removed and
    whitespace is collapsed. Used to judge whether a page has usable content.

    :param markdown: markdown text.
    :returns: the visible text, single-spaced.
    """
    text = _MD_IMAGE_RE.sub(r"\1", markdown or "")
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_BARE_URL_RE.sub(" ", text)
    text = _MD_SYNTAX_RE.sub(" ", text)
    return " ".join(text.split())


def usable_content_verdict(raw: str, markdown: str) -> str | None:
    """Judge whether a fetched URL page carries usable content (AC9).

    :param raw: the raw response body (HTML or text) before conversion.
    :param markdown: the converted, boilerplate-stripped markdown.
    :returns: ``None`` for a usable page, else the refusal reason: ``empty``,
        ``challenge_page``, ``js_shell`` or ``too_little_text (<n> chars)``.
        Interstitial markers (Cloudflare ``cf-chl``, "Just a moment...",
        "Checking your browser", "Attention Required") count on a page under
        2,000 visible chars; captcha widgets (``g-recaptcha``, ``h-captcha``,
        ``cf-turnstile``) only on a page under 300, since ordinary forms carry
        them too. An empty app mount
        point (``div#root|app|__next``) or a page whose only text is a
        ``<noscript>`` notice is a JavaScript shell.
    """
    if not (raw or "").strip():
        return "empty"
    visible = markdown_visible_text(markdown)
    is_html = _looks_like_html(raw) or "<body" in raw.lower() or "<div" in raw.lower()
    if is_html:
        lowered = raw.lower()
        if len(visible) < _CHALLENGE_MAX_VISIBLE_CHARS and any(
            marker in lowered for marker in _CHALLENGE_MARKERS
        ):
            return "challenge_page"
        if len(visible) < _MIN_VISIBLE_CHARS and any(
            marker in lowered for marker in _CAPTCHA_MARKERS
        ):
            return "challenge_page"
        if len(visible) < _MIN_VISIBLE_CHARS and _is_js_shell(raw):
            return "js_shell"
    if not visible:
        return "empty"
    if len(visible) < _MIN_VISIBLE_CHARS:
        return f"too_little_text ({len(visible)} chars)"
    return None


def _is_js_shell(raw: str) -> bool:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for el in soup(["script", "style", "template"]):
        el.decompose()
    mount = soup.find("div", id=_JS_MOUNT_IDS)
    if mount is not None and not _visible_text(mount):
        return True
    notices = soup.find_all("noscript")
    if not notices:
        return False
    notice_text = " ".join(_visible_text(n) for n in notices)
    for n in notices:
        n.decompose()
    return "javascript" in notice_text.lower() and not _visible_text(soup.body or soup)


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:256].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _fetch_remote_raw(url_str: str) -> tuple[str, str]:
    """Manual redirect loop with per-hop SSRF validation and a size cap.

    Returns ``(decoded_body, content_type)``.
    """
    max_bytes = _max_bytes()
    timeout = httpx.Timeout(connect=5, read=15, write=5, pool=5)
    current = httpx.URL(url_str)

    with httpx.Client(
        follow_redirects=False, timeout=timeout, headers={"User-Agent": USER_AGENT}
    ) as client:
        for _hop in range(_MAX_REDIRECTS + 1):
            _assert_url_safe(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("Location")
                    if not location:
                        resp.read()
                        raise SsrfBlocked("redirect without Location header")
                    current = httpx.URL(str(current.join(location)))
                    continue
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "pdf" in content_type.lower():
                    raise SsrfBlocked(
                        "PDF sources are not supported in v0.3.0; "
                        "provide a local markdown/text file instead"
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        chunks.append(chunk[: max(0, max_bytes - (total - len(chunk)))])
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)[:max_bytes]
                text = raw.decode(resp.encoding or "utf-8", errors="replace")
                return text, content_type

    raise SsrfBlocked(f"too many redirects (>{_MAX_REDIRECTS})")


def _fetch_file(source: str) -> str:
    """Read a local file; HTML files are converted to markdown."""
    path = Path(source)
    if not path.exists():
        return f"[DATA ERROR] file_not_found: {source}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"[DATA ERROR] file_read_failed: {source} ({exc})"
    if path.suffix.lower() in (".html", ".htm"):
        return _to_markdown(text, "text/html")
    return text


def fetch_url(source: str) -> str:
    """Fetch ``source`` (http/https URL or local file path) and return markdown.

    SSRF rejections and unsupported content surface as a ``[DATA ERROR]`` string
    (containing ``ssrf_blocked`` for blocked addresses) rather than raising, so
    the ingest pipeline can short-circuit on the returned value. Delegates to
    ``fetch_source`` and returns its ``markdown``.
    """
    return fetch_source(source)["markdown"]


def _is_http_url(source: str) -> tuple[bool, str]:
    try:
        scheme = httpx.URL(source).scheme
    except (httpx.InvalidURL, ValueError, TypeError):
        scheme = ""
    return scheme in ("http", "https"), scheme


def fetch_source(source: str) -> dict:
    """Fetch ``source`` like ``fetch_url`` and judge a URL page's usable content.

    Returns ``{"markdown", "raw", "content_type", "is_url", "unusable"}``:
    ``markdown`` is exactly what ``fetch_url`` returns (a ``[DATA ERROR]`` string
    on failure); ``raw`` and ``content_type`` are the undecoded-to-markdown body
    and its type for a fetched URL (``None`` otherwise); ``unusable`` is the
    ``usable_content_verdict`` reason for a fetched URL page, else ``None``.
    Local files and fetch errors never get a verdict (ingest keeps its
    ``empty_source`` path for files).
    """
    is_url, scheme = _is_http_url(source)
    out = {
        "markdown": "",
        "raw": None,
        "content_type": None,
        "is_url": is_url,
        "unusable": None,
    }
    if not is_url:
        # Anything that is not an http(s) URL is a local file path. A stray
        # non-http scheme (file://, ftp://) is rejected as ssrf_blocked.
        if "://" in source and scheme:
            out["markdown"] = f"[DATA ERROR] ssrf_blocked: scheme not allowed: {scheme}"
        else:
            out["markdown"] = _fetch_file(source)
        return out
    try:
        raw, content_type = _fetch_remote_raw(source)
    except SsrfBlocked as exc:
        out["markdown"] = f"[DATA ERROR] ssrf_blocked: {exc}"
        return out
    except httpx.HTTPError as exc:
        out["markdown"] = f"[DATA ERROR] fetch_failed: {exc}"
        return out
    markdown = _to_markdown(raw, content_type)
    out.update(
        markdown=markdown,
        raw=raw,
        content_type=content_type,
        unusable=usable_content_verdict(raw, markdown),
    )
    return out
