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
import socket
from pathlib import Path

import httpx

from . import config

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


def _to_markdown(text: str, content_type: str) -> str:
    """Convert HTML to markdown; pass plain text/markdown through unchanged."""
    if "html" in (content_type or "").lower() or _looks_like_html(text):
        from markdownify import markdownify as _md

        return _md(text, heading_style="ATX")
    return text


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:256].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _fetch_remote(url_str: str) -> str:
    """Manual redirect loop with per-hop SSRF validation and a size cap."""
    max_bytes = _max_bytes()
    timeout = httpx.Timeout(connect=5, read=15, write=5, pool=5)
    current = httpx.URL(url_str)

    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
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
                return _to_markdown(text, content_type)

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
    the ingest pipeline can short-circuit on the returned value.
    """
    scheme = ""
    try:
        scheme = httpx.URL(source).scheme
    except (httpx.InvalidURL, ValueError, TypeError):
        scheme = ""

    if scheme not in ("http", "https"):
        # Treat anything that is not an http(s) URL as a local file path. A
        # stray non-http scheme (file://, ftp://) is rejected as ssrf_blocked.
        if "://" in source and scheme:
            return f"[DATA ERROR] ssrf_blocked: scheme not allowed: {scheme}"
        return _fetch_file(source)

    try:
        return _fetch_remote(source)
    except SsrfBlocked as exc:
        return f"[DATA ERROR] ssrf_blocked: {exc}"
    except httpx.HTTPError as exc:
        return f"[DATA ERROR] fetch_failed: {exc}"
