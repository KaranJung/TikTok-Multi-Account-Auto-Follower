"""
Free Proxy Finder & Tester for TikTok Automation.

Features:
1. Validates that the proxy actually tunnels HTTPS to TikTok and returns authentic TikTok content
   (tiktok.com / ttwstatic / __UNIVERSAL_DATA_FOR_REHYDRATION__ markers) rather than captive portals or fake 200 responses.
2. Expands active proxy feeds across the web and increases concurrency for faster filtering.
3. Clean percentage progress updates (.....10% LOADED) and arranged summary table.
No emojis used.
"""
from __future__ import annotations

import json
import math
import re
import time
from ipaddress import IPv4Address
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional
from pathlib import Path

from rich.table import Table
from rich.align import Align
from rich import box

from utils.logger import log_info, log_success, log_warning, log_error, console

PROXY_SOURCES: List[Dict[str, Any]] = [
    {"name": "FlashProxy API (1000)",     "limit": 1000, "url": "https://www.flashproxy.com/api/proxies/txt?limit=1000"},
    {"name": "ProxyScrape HTTPS CONNECT API", "url": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=http&ssl=yes&timeout=3000&limit=350&proxy_format=protocolipport&format=text"},
    {"name": "ProxyScrape SOCKS5 API", "scheme": "socks5", "url": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=3000&limit=350&proxy_format=protocolipport&format=text"},
    {"name": "GeoNode HTTPS CONNECT API", "format": "geonode", "url": "https://proxylist.geonode.com/api/proxy-list?limit=350&page=1&sort_by=latency&sort_type=asc&protocols=https"},
    {"name": "Proxifly HTTPS Stream", "scheme": "https", "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/https/data.txt"},
    {"name": "IPLocate HTTP Pool", "url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt"},
    {"name": "IPLocate HTTPS Pool", "scheme": "https", "url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/https.txt"},
    {"name": "Zaeem20 HTTPS CONNECT Pool", "url": "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt"},
    {"name": "SSLProxies.org",           "url": "https://www.sslproxies.org/"},
    {"name": "FreeProxyList.net",        "url": "https://free-proxy-list.net/"},
    {"name": "US-Proxy.org",             "url": "https://www.us-proxy.org/"},
    {"name": "Anonymous Proxies",        "url": "https://free-proxy-list.net/anonymous-proxy.html"},
    {"name": "Spys.me Live HTTP",        "url": "https://spys.me/proxy.txt"},
    {"name": "Spys.me Live SOCKS",       "scheme": "socks5", "url": "https://spys.me/socks.txt"},
    {"name": "Proxifly HTTP Stream",     "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt"},
    {"name": "Proxifly SOCKS5 Stream",   "scheme": "socks5", "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt"},
    {"name": "TheSpeedX HTTP Pool",      "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"},
    {"name": "TheSpeedX SOCKS5 Pool",    "scheme": "socks5", "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"},
    {"name": "Monosans Checked Pool",    "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"},
    {"name": "Monosans SOCKS5 Pool",     "scheme": "socks5", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"},
    {"name": "Vakhov Fresh Proxies",     "url": "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt"},
    {"name": "Vakhov SOCKS5 Proxies",    "scheme": "socks5", "url": "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt"},
    {"name": "RoosterKid HTTPS",         "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"},
    {"name": "RoosterKid SOCKS5",        "scheme": "socks5", "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"},
]

PROFILE_TEST_URL       = "https://www.tiktok.com/@tiktok"
TEST_TIMEOUT           = 6
MAX_PROXY_LATENCY      = 2.5
MAX_TEST_WORKERS       = 80
MAX_COLLECT_PER_SOURCE = 350
MAX_WORKING            = 30


def _normalize_candidate(value: str, default_scheme: str = "http") -> Optional[str]:
    try:
        parsed = urlsplit(value if "://" in value else f"{default_scheme}://{value}")
        if parsed.scheme not in ("http", "https", "socks4", "socks5"):
            return None
        address = IPv4Address(parsed.hostname or "")
        port = parsed.port
        if not address.is_global or address.is_multicast or address.is_reserved:
            return None
        if not port or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return None
        return f"{parsed.scheme}://{address}:{port}"
    except ValueError:
        return None


def _extract_proxies_from_payload(
    text: str, default_scheme: str = "http", source_format: str = "text"
) -> List[str]:
    candidates = []
    if source_format == "geonode":
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return []
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []
        for row in rows:
            if not isinstance(row, dict):
                continue
            protocols = row.get("protocols", [])
            if not isinstance(protocols, list):
                continue
            # GeoNode labels HTTP CONNECT support as HTTPS, not TLS-to-proxy.
            if any(protocol in ("http", "https") for protocol in protocols):
                candidates.append(f"http://{row.get('ip')}:{row.get('port')}")
    else:
        for ip, port in re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*(\d{1,3}(?:\.\d{1,3}){3})\s*</td>\s*<td[^>]*>\s*(\d{1,5})\s*</td>", text, re.IGNORECASE):
            candidates.append(f"{ip}:{port}")
        candidates.extend(re.findall(
            r"(?<![\w.:/@-])(?:[a-z][a-z0-9+.-]*://)?\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}(?![\w.:/@-])",
            text, re.IGNORECASE,
        ))

    # Preserve feed ordering while deduplicating protocol-aware endpoints.
    found = {}
    for value in candidates:
        server = _normalize_candidate(value, default_scheme)
        if server:
            found.setdefault(server, None)
    return list(found)


def _fetch_from_source(source: Dict[str, Any]) -> List[str]:
    url = source["url"]
    try:
        from curl_cffi import requests as cffi
        with cffi.Session(impersonate="chrome131") as session:
            response = session.get(url, timeout=10, verify=True)
            if response.status_code != 200:
                log_warning(f"Proxy source {source['name']}: HTTP {response.status_code}")
                return []
            items = _extract_proxies_from_payload(
                response.text, source.get("scheme", "http"), source.get("format", "text")
            )
            limit = int(source.get("limit", MAX_COLLECT_PER_SOURCE))
            return items[:limit]
    except Exception:
        return []


def _test_proxy_on_tiktok(
    proxy_str: str, max_latency: float = MAX_PROXY_LATENCY
) -> Optional[Dict[str, Any]]:
    """
    Strictly verifies that the proxy:
    1. Supports HTTPS CONNECT tunneling to www.tiktok.com without MITM gateway injection
    2. Returns authentic TikTok HTML content (tiktok / ttwstatic / __UNIVERSAL_DATA_FOR_REHYDRATION__)
    3. Is not blocked with 403 Forbidden or Access Denied
    """
    server = _normalize_candidate(proxy_str.strip())
    if not server or not math.isfinite(max_latency) or max_latency <= 0:
        return None
    try:
        from curl_cffi import requests as cffi
        # No account cookies are sent during public proxy checks.
        with cffi.Session(impersonate="chrome131", trust_env=False) as session:
            session.proxies = {"http": server, "https": server}
            t0 = time.monotonic()
            r = session.get(
                PROFILE_TEST_URL, timeout=min(TEST_TIMEOUT, max_latency),
                verify=True, allow_redirects=False,
            )
            latency = time.monotonic() - t0
            body = r.text.lower()
            final_url = urlsplit(r.url)

            # Validates genuine TikTok response
            is_valid_tiktok = (
                r.status_code == 200
                and final_url.scheme == "https"
                and final_url.hostname == "www.tiktok.com"
                and ("ttwstatic" in body or "__universal_data_for_rehydration__" in body)
                and "forbidden" not in body
                and "access denied" not in body
                and "verify you are human" not in body
                and len(r.text) > 400
                and latency <= max_latency
            )

            if is_valid_tiktok:
                return {"server": server, "_latency": round(latency, 3)}
    except Exception:
        pass
    return None


def _latency_bar(lat: float) -> str:
    if lat < 1.0:
        return "[bold green]FAST[/bold green]"
    if lat < 2.5:
        return "[bold yellow]OK  [/bold yellow]"
    return "[bold red]SLOW[/bold red]"


def _print_proxy_table(working: List[Dict[str, Any]]) -> None:
    table = Table(
        title=f"[bold white]COLLECTED PROXIES FOR USE ({len(working)})[/bold white]",
        box=box.ROUNDED,
        border_style="#25F4EE",
        header_style="bold #FE2C55",
        expand=False,
    )
    table.add_column("#",        style="bold white",   justify="right",  width=4)
    table.add_column("Proxy",    style="bold #25F4EE", justify="left",   min_width=26)
    table.add_column("Latency",  style="white",        justify="center", width=10)
    table.add_column("Speed",    justify="center",     width=8)
    table.add_column("Protocol", style="dim white",    justify="center", width=8)

    for i, p in enumerate(working, 1):
        server  = p.get("server", "")
        latency = p.get("_latency", 0.0)
        scheme  = server.split("://")[0].upper() if "://" in server else "HTTP"
        host    = server.split("://")[-1]
        table.add_row(
            str(i),
            host,
            f"{latency:.2f}s",
            _latency_bar(latency),
            scheme,
        )

    console.print("")
    console.print(Align.left(table))
    console.print("")


def collect_and_test_proxies(
    min_working: int = 5,
    max_working: int = MAX_WORKING,
    max_latency: float = MAX_PROXY_LATENCY,
) -> List[Dict[str, Any]]:
    if not 1 <= min_working <= max_working:
        raise ValueError("Require 1 <= min_working <= max_working")
    if not math.isfinite(max_latency) or max_latency <= 0:
        raise ValueError("max_latency must be a positive finite number")
    console.print("\n[bold #25F4EE]PLEASE WAIT WE ARE TESTING AND COLLECTING PROXIES[/bold #25F4EE]\n")

    raw_candidates: List[str] = []
    with ThreadPoolExecutor(max_workers=len(PROXY_SOURCES)) as pool:
        futures = {pool.submit(_fetch_from_source, src): src for src in PROXY_SOURCES}
        for fut in as_completed(futures):
            try:
                batch = fut.result()
                raw_candidates.extend(batch)
                log_info(f"{futures[fut]['name']}: {len(batch)} candidates")
            except Exception:
                pass

    seen: set = set()
    unique: List[str] = []
    for p in raw_candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    if not unique:
        log_error("Could not fetch any proxy candidates. Please check internet connection.")
        return []

    log_info(f"Scraped {len(unique)} unique proxy candidates. Checking TikTok HTTPS access within {max_latency:.1f}s...")

    working_with_latency: List[Dict[str, Any]] = []
    tested = 0
    stop_early = False
    last_reported_milestone = 0

    with ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as pool:
        futures_map = {pool.submit(_test_proxy_on_tiktok, p, max_latency): p for p in unique}
        for fut in as_completed(futures_map):
            tested += 1
            try:
                result = fut.result()
            except Exception:
                result = None

            if result:
                working_with_latency.append(result)
                if len(working_with_latency) >= max_working:
                    stop_early = True

            pct_by_working = (len(working_with_latency) / max_working) * 100
            pct_by_tested = (tested / len(unique)) * 100
            current_pct = min(100, int(max(pct_by_working, pct_by_tested)))
            target_milestone = (current_pct // 10) * 10

            while last_reported_milestone + 10 <= target_milestone and last_reported_milestone < 100:
                last_reported_milestone += 10
                dots = "." * (1 + (last_reported_milestone // 10) * 4)
                working_count = len(working_with_latency)
                console.print(
                    f"[bold #25F4EE]{dots}{last_reported_milestone}% LOADED[/bold #25F4EE]  "
                    f"[dim]({working_count} active proxies ready)[/dim]"
                )

            if stop_early:
                for pending in futures_map:
                    pending.cancel()
                break

    if working_with_latency and last_reported_milestone < 100:
        while last_reported_milestone < 100:
            last_reported_milestone += 10
            dots = "." * (1 + (last_reported_milestone // 10) * 4)
            working_count = len(working_with_latency)
            console.print(
                f"[bold #25F4EE]{dots}{last_reported_milestone}% LOADED[/bold #25F4EE]  "
                f"[dim]({working_count} active proxies ready)[/dim]"
            )

    working_with_latency.sort(key=lambda x: x.get("_latency", 99))

    if working_with_latency:
        _print_proxy_table(working_with_latency)

    working = []
    for w in working_with_latency:
        entry = {k: v for k, v in w.items() if k != "_latency"}
        working.append(entry)

    if working:
        log_success(
            f"[bold green]{len(working)}[/bold green] proxies passed the TikTok HTTPS page check within {max_latency:.1f}s, sorted fastest first."
        )
        if len(working) < min_working:
            log_warning(f"Only {len(working)} of the requested minimum {min_working} proxies passed.")
        log_warning("Public proxies are untrusted and can expire quickly. Page access does not guarantee login or follow success.")
    else:
        log_warning(f"No public proxies passed the verified TikTok HTTPS page check within {max_latency:.1f}s. Existing proxy files were not changed.")

    return working


def save_proxies_to_file(proxies: List[Dict[str, Any]], path: str = "proxies.txt") -> None:
    lines = []
    for p in proxies:
        server   = p.get("server", "")
        username = p.get("username", "")
        password = p.get("password", "")
        if username and password:
            scheme, rest = server.split("://", 1)
            lines.append(f"{scheme}://{username}:{password}@{rest}")
        else:
            lines.append(server)

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    log_success(f"Saved {len(proxies)} proxies to [bold white]{path}[/bold white]")
