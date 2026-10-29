"""
Free Proxy Finder & Tester for TikTok Automation.

Aggregates live proxies across the internet:
- Public Proxy Websites & Web Aggregators (ProxyScrape, SSLProxies.org, FreeProxyList.net, US-Proxy, Spys.me)
- Global Verified Proxy Streams (Proxifly, Thordata, TheSpeedX, Monosans, RoosterKid)

Directly tests candidates against https://www.tiktok.com using curl_cffi Chrome131 TLS.
Rejects any proxy that triggers 403 Forbidden, SSL handshake errors, or Cloudflare blocks.

No emojis used. Clean percentage progress updates and arranged summary table.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional
from pathlib import Path

from rich.table import Table
from rich.align import Align
from rich import box

from utils.logger import log_info, log_success, log_warning, log_error, console

# ---------------------------------------------------------------------------
# Global Free Proxy Sources (Websites, Live APIs, and High-Speed Streams)
# ---------------------------------------------------------------------------
PROXY_SOURCES: List[Dict[str, str]] = [
    # 1. Live Websites & Web APIs
    {"name": "ProxyScrape HTTP API",    "url": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"},
    {"name": "ProxyScrape SOCKS5 API",  "url": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all"},
    {"name": "SSLProxies.org",          "url": "https://www.sslproxies.org/"},
    {"name": "FreeProxyList.net",       "url": "https://free-proxy-list.net/"},
    {"name": "US-Proxy.org",            "url": "https://www.us-proxy.org/"},
    {"name": "UK-Proxy (FreeProxyList)","url": "https://free-proxy-list.net/uk-proxy.html"},
    {"name": "Anonymous Proxies",       "url": "https://free-proxy-list.net/anonymous-proxy.html"},
    {"name": "Spys.me Live HTTP",       "url": "https://spys.me/proxy.txt"},
    {"name": "Spys.me Live SOCKS",      "url": "https://spys.me/socks.txt"},

    # 2. Continuous Global Verified Streams
    {"name": "Proxifly HTTP Stream",    "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt"},
    {"name": "Proxifly SOCKS5 Stream",  "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt"},
    {"name": "Thordata Awesome Proxies","url": "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/all.txt"},
    {"name": "TheSpeedX HTTP Pool",     "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"},
    {"name": "TheSpeedX SOCKS5 Pool",   "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"},
    {"name": "Monosans Checked Pool",   "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"},
    {"name": "RoosterKid HTTPS",        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"},
    {"name": "RoosterKid SOCKS5",       "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"},
    {"name": "ShiftyTR Active List",    "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"},
    {"name": "Sunny9577 Live Scrape",   "url": "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt"},
]

TEST_URL            = "https://www.tiktok.com"
TEST_TIMEOUT        = 6    # seconds per proxy against TikTok
MAX_TEST_WORKERS    = 70   # parallel checking threads
MAX_COLLECT_PER_SOURCE = 350
MAX_WORKING         = 30   # target number of verified TikTok proxies


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_proxies_from_payload(text: str) -> List[str]:
    """
    Extracts clean ip:port strings from any format:
    - HTML table rows (<tr><td>IP</td><td>PORT</td>) from sites like sslproxies.org
    - Raw text lists (one ip:port per line)
    - JSON or textareas
    """
    found = set()

    # 1. HTML table format
    for ip, port in re.findall(r"<tr>\s*<td>(\d{1,3}(?:\.\d{1,3}){3})</td>\s*<td>(\d{2,5})</td>", text, re.IGNORECASE):
        found.add(f"{ip}:{port}")

    # 2. General ip:port tokens anywhere in response
    for match in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b", text):
        found.add(match)

    return list(found)


def _fetch_from_source(source: Dict[str, str]) -> List[str]:
    """Fetch proxy candidates from a given website or endpoint."""
    url = source["url"]
    try:
        from curl_cffi import requests as cffi
        s = cffi.Session(impersonate="chrome131")
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        r = s.get(url, timeout=10)
        if r.status_code != 200:
            return []
        items = _extract_proxies_from_payload(r.text)
        return items[:MAX_COLLECT_PER_SOURCE]
    except Exception:
        return []


def _test_proxy_on_tiktok(proxy_str: str) -> Optional[Dict[str, Any]]:
    """
    Test a proxy directly against https://www.tiktok.com using Chrome 131 TLS.
    Tries HTTP proxy tunnel, falls back to SOCKS5 if candidate is a SOCKS proxy.
    Returns Playwright-compatible proxy dict with latency if status is 200 OK.
    Rejects any proxy that triggers 403 Forbidden or connection error.
    """
    raw = proxy_str.split("://")[-1].strip()
    schemes = ["http", "socks5"]

    for scheme in schemes:
        server = f"{scheme}://{raw}"
        try:
            from curl_cffi import requests as cffi
            s = cffi.Session(impersonate="chrome131")
            s.proxies = {"http": server, "https": server}
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            t0 = time.monotonic()
            r = s.get(TEST_URL, timeout=TEST_TIMEOUT, verify=False)
            latency = time.monotonic() - t0

            # Verified clean response from TikTok
            if r.status_code == 200 and "forbidden" not in r.text.lower() and len(r.text) > 400:
                return {"server": server, "_latency": round(latency, 2)}
        except Exception:
            pass
    return None


def _latency_bar(lat: float) -> str:
    """Return a clean speed indicator based on latency in seconds."""
    if lat < 0.6:
        return "[bold green]FAST[/bold green]"
    if lat < 1.5:
        return "[bold yellow]OK  [/bold yellow]"
    return "[bold red]SLOW[/bold red]"


def _print_proxy_table(working: List[Dict[str, Any]]) -> None:
    """Render a clean arranged numbered table of all verified working proxies."""
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_and_test_proxies(
    min_working: int = 5,
    max_working: int = MAX_WORKING,
) -> List[Dict[str, Any]]:
    """
    1. Shows initial notification: PLEASE WAIT WE ARE TESTING AND COLLECTING PROXIES
    2. Scrapes websites & APIs silently in parallel across the web.
    3. Tests candidates directly against TikTok with parallel threads.
    4. Prints progressive updates in percent:
         .....10% LOADED
         .........20% LOADED
         ...
         .........................................100% LOADED
    5. Displays arranged clean table of working proxies sorted by speed.
    """
    console.print("\n[bold #25F4EE]PLEASE WAIT WE ARE TESTING AND COLLECTING PROXIES[/bold #25F4EE]\n")

    # Step 1: Fetch from all web sources in parallel
    raw_candidates: List[str] = []
    with ThreadPoolExecutor(max_workers=len(PROXY_SOURCES)) as pool:
        futures = {pool.submit(_fetch_from_source, src): src for src in PROXY_SOURCES}
        for fut in as_completed(futures):
            try:
                batch = fut.result()
                raw_candidates.extend(batch)
            except Exception:
                pass

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for p in raw_candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    if not unique:
        log_error("Could not fetch any proxy candidates. Please check internet connection.")
        return []

    # Step 2: Test concurrently against TikTok and print progressive percent updates
    working_with_latency: List[Dict[str, Any]] = []
    tested = 0
    stop_early = False
    last_reported_milestone = 0

    with ThreadPoolExecutor(max_workers=MAX_TEST_WORKERS) as pool:
        futures_map = {pool.submit(_test_proxy_on_tiktok, p): p for p in unique}
        for fut in as_completed(futures_map):
            if stop_early:
                fut.cancel()
                continue
            tested += 1
            try:
                result = fut.result()
            except Exception:
                result = None

            if result:
                working_with_latency.append(result)
                if len(working_with_latency) >= max_working:
                    stop_early = True

            # Calculate current percentage (progress toward target proxies or completed candidates)
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

    # Ensure progress reaches 100% when testing finishes or target is met
    if working_with_latency and last_reported_milestone < 100:
        while last_reported_milestone < 100:
            last_reported_milestone += 10
            dots = "." * (1 + (last_reported_milestone // 10) * 4)
            working_count = len(working_with_latency)
            console.print(
                f"[bold #25F4EE]{dots}{last_reported_milestone}% LOADED[/bold #25F4EE]  "
                f"[dim]({working_count} active proxies ready)[/dim]"
            )

    # Step 3: Sort by speed (fastest first)
    working_with_latency.sort(key=lambda x: x.get("_latency", 99))

    # Step 4: Render clean arranged summary table
    if working_with_latency:
        _print_proxy_table(working_with_latency)

    # Clean internal key before returning
    working = []
    for w in working_with_latency:
        entry = {k: v for k, v in w.items() if k != "_latency"}
        working.append(entry)

    if working:
        log_success(
            f"[bold green]{len(working)}[/bold green] working proxies verified on TikTok and ready for rotation."
        )
    else:
        log_warning("No working proxies found. You can add your own into proxies.txt.")

    return working


def save_proxies_to_file(proxies: List[Dict[str, Any]], path: str = "proxies.txt") -> None:
    """Write working proxy list to file, overwriting previous content."""
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
