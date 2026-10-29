"""
TikTok Cookie Analyzer & Account Auditor.
Extracts geographic registration metadata (store-country-code), datacenter IDC (tt-target-idc),
session integrity, follower/following statistics, and account active/deactivated status.
No emojis used.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional
import collections

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box

from utils.cookie_parser import parse_cookie_file
from utils.logger import console

COUNTRY_MAP = {
    "br": "Brazil",
    "es": "Spain",
    "fr": "France",
    "vn": "Vietnam",
    "ph": "Philippines",
    "id": "Indonesia",
    "pl": "Poland",
    "us": "United States",
    "pe": "Peru",
    "it": "Italy",
    "de": "Germany",
    "gb": "United Kingdom",
    "uk": "United Kingdom",
    "mx": "Mexico",
    "co": "Colombia",
    "ar": "Argentina",
    "cl": "Chile",
    "tr": "Turkey",
    "ru": "Russia",
    "ua": "Ukraine",
    "th": "Thailand",
    "my": "Malaysia",
    "sg": "Singapore",
    "jp": "Japan",
    "kr": "South Korea",
    "in": "India",
    "np": "Nepal",
    "ca": "Canada",
    "au": "Australia",
    "ro": "Romania",
    "dz": "Algeria",
    "ae": "United Arab Emirates",
    "iq": "Iraq",
    "kw": "Kuwait",
    "cm": "Cameroon",
    "gr": "Greece",
    "lk": "Sri Lanka",
    "ps": "Palestine",
    "za": "South Africa",
    "rs": "Serbia",
    "ec": "Ecuador",
}

IDC_MAP = {
    "alisg": "Alibaba Cloud (Singapore / SE Asia / LATAM)",
    "eu-ttp2": "European Datacenter (EU / UK)",
    "us-eastred": "US East Cluster (Virginia / US)",
    "useast5": "US East Cluster 5 (North America)",
    "useast8": "US East Cluster 8 (North America)",
    "my": "Malaysia IDC Cluster",
}


def extract_username_from_filename(filename: str) -> str:
    match = re.search(r"@([a-zA-Z0-9_.]+)", filename)
    if match:
        return match.group(1).rstrip("/")
    brackets = re.findall(r"\[(.*?)\]", filename)
    for b in brackets:
        b_clean = b.strip()
        low = b_clean.lower()
        if not any(k in low for k in ("alive", "dead", "checked", "software", "hydra", "valid", "cookie")):
            return b_clean
    clean = re.sub(r"\[.*?\]", "", filename)
    clean = clean.replace(".txt", "").replace(".json", "").strip()
    return clean or "Unknown"


def scan_cookie_metadata(file_path: Path) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "username": extract_username_from_filename(file_path.name),
        "uid": "",
        "country_code": "unknown",
        "country_name": "Unknown",
        "idc": "unknown",
        "idc_name": "Unknown",
        "has_session": False,
        "has_ttwid": False,
        "has_odin": False,
        "total_cookies": 0,
        "parse_error": False,
        "status": "Unknown",
        "followers": None,
        "following": None,
        "likes": None,
        "videos": None,
        "is_private": None,
        "deactivated": False,
        "detail": ""
    }

    try:
        cookies = parse_cookie_file(file_path)
    except Exception as e:
        record["parse_error"] = True
        record["status"] = "Corrupted File"
        record["detail"] = f"Failed to parse cookie format: {e}"
        return record

    record["total_cookies"] = len(cookies)
    cookie_map: Dict[str, str] = {}
    for c in cookies:
        name = c.get("name", "")
        if name:
            cookie_map[name] = c.get("value", "")

    # Extract Country
    country = cookie_map.get("store-country-code", "").strip().lower()
    if not country:
        for k, v in cookie_map.items():
            if "country" in k.lower() and len(v) == 2:
                country = v.lower()
                break
    if country:
        record["country_code"] = country
        record["country_name"] = COUNTRY_MAP.get(country, country.upper())

    # Extract Target Datacenter IDC
    idc = cookie_map.get("tt-target-idc", "").strip().lower()
    if not idc:
        idc = cookie_map.get("store-idc", "").strip().lower()
    if idc:
        record["idc"] = idc
        record["idc_name"] = IDC_MAP.get(idc, idc)

    # Extract UID
    uid = cookie_map.get("uid_tt", "") or cookie_map.get("uid_tt_ss", "")
    if uid:
        record["uid"] = uid

    # Validate essential auth cookies
    has_session = any(k in cookie_map for k in ("sessionid", "sessionid_ss", "sid_tt"))
    record["has_session"] = has_session
    record["has_ttwid"] = "ttwid" in cookie_map
    record["has_odin"] = "odin_tt" in cookie_map

    if not has_session:
        record["status"] = "No Session"
        record["detail"] = "Missing sessionid / sid_tt cookie"
    else:
        record["status"] = "Active Session"
        record["detail"] = f"Country: {record['country_name']} | IDC: {record['idc']}"

    return record


def audit_account_live(record: Dict[str, Any], browser_context, timeout: int = 25) -> Dict[str, Any]:
    file_path = Path(record["file_path"])
    try:
        cookies = parse_cookie_file(file_path)
    except Exception:
        record["status"] = "Invalid File"
        return record

    username = record["username"]
    page = browser_context.new_page()
    try:
        browser_context.clear_cookies()
        browser_context.add_cookies(cookies)

        # Audit profile page
        target_url = f"https://www.tiktok.com/@{username}" if username != "Unknown" else "https://www.tiktok.com/"
        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(3500)

        data = page.evaluate("""() => {
            try {
                const body = document.body ? document.body.innerText.toLowerCase() : '';
                const isDeactivated = body.includes("couldn't find this account") ||
                                      body.includes("account not found") ||
                                      body.includes("user does not exist") ||
                                      body.includes("account is currently unavailable");

                const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (!el) {
                    return { isDeactivated, hasHydration: false };
                }
                const d = JSON.parse(el.textContent);
                const scope = d?.['__DEFAULT_SCOPE__'] || {};
                const ud = scope?.['webapp.user-detail'];
                const user = ud?.userInfo?.user;
                const stats = ud?.userInfo?.stats;
                const appUser = scope?.['webapp.app-context']?.user;
                const statusCode = ud?.statusCode;

                const deactivatedFlag = isDeactivated || statusCode === 10221 || statusCode === 10202;
                return {
                    isDeactivated: deactivatedFlag,
                    hasHydration: true,
                    loggedIn: !!(appUser && appUser.uid),
                    appUid: appUser ? String(appUser.uid) : null,
                    username: user?.uniqueId || appUser?.uniqueId || null,
                    nickname: user?.nickname || appUser?.nickName || null,
                    followers: stats?.followerCount ?? 0,
                    following: stats?.followingCount ?? 0,
                    likes: stats?.heartCount ?? 0,
                    videos: stats?.videoCount ?? 0,
                    private: !!user?.secret
                };
            } catch (e) {
                return { error: String(e) };
            }
        }""")

        if data.get("isDeactivated"):
            record["deactivated"] = True
            record["status"] = "Deactivated / Banned"
            record["detail"] = "Account deleted, banned, or not found on TikTok"
        elif data.get("loggedIn"):
            record["status"] = "Active"
            record["followers"] = data.get("followers", 0)
            record["following"] = data.get("following", 0)
            record["likes"] = data.get("likes", 0)
            record["videos"] = data.get("videos", 0)
            record["is_private"] = data.get("private", False)
            if data.get("username"):
                record["username"] = data["username"]
            if data.get("appUid"):
                record["uid"] = data["appUid"]
            record["detail"] = f"Followers: {record['followers']} | Following: {record['following']} | Videos: {record['videos']}"
        elif "/login" in page.url or data.get("hasHydration") is True:
            record["status"] = "Expired Session"
            record["detail"] = "Session credentials expired or logged out"
        else:
            record["status"] = "Active (Unconfirmed)"
            record["detail"] = "Profile loaded; full hydration state pending"

    except Exception as e:
        record["status"] = "Audit Error"
        record["detail"] = f"Browser evaluation failed: {type(e).__name__}"
    finally:
        try:
            page.close()
        except Exception:
            pass

    return record


def print_ascii_header():
    header_text = (
        "[bold white]TIKTOK COOKIE ANALYZER & ACCOUNT AUDITOR[/bold white]\n"
        "[dim]Geographic Registration Scan  •  Datacenter Mapping  •  Health & Deactivation Check[/dim]\n\n"
        "[bold #25F4EE]Developer:[/bold #25F4EE] [white]@hydra_X001[/white]    "
        "[bold #FE2C55]Telegram:[/bold #FE2C55] [underline blue]https://t.me/hydrax001[/underline blue]"
    )
    panel = Panel(
        Align.center(header_text),
        box=box.ROUNDED,
        border_style="#FE2C55",
        padding=(1, 2),
        expand=False
    )
    console.print(panel)


def display_results_table(records: List[Dict[str, Any]], deep: bool = False):
    table = Table(
        title=f"\n[bold white]COOKIE ACCOUNTS AUDIT REPORT ({len(records)} ACCOUNTS)[/bold white]",
        box=box.ROUNDED,
        border_style="#25F4EE",
        header_style="bold #FE2C55",
        expand=False
    )
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Account File", style="white", justify="left", min_width=24)
    table.add_column("Username", style="bold #25F4EE", justify="left", min_width=15)
    table.add_column("Country (store-country-code)", style="bold yellow", justify="center", width=18)
    table.add_column("Datacenter (tt-target-idc)", style="cyan", justify="center", width=18)
    table.add_column("Status", justify="center", width=16)

    if deep:
        table.add_column("Followers", style="green", justify="right", width=10)
        table.add_column("Following", style="white", justify="right", width=10)
        table.add_column("Videos", style="white", justify="right", width=8)

    table.add_column("Details", style="dim", justify="left", min_width=25)

    for idx, r in enumerate(records, 1):
        status_style = "bold green" if r["status"] == "Active" or r["status"] == "Active Session" else \
                       "bold red" if "Deactivated" in r["status"] or "Expired" in r["status"] else "yellow"

        row = [
            str(idx),
            r["file_name"][:28] + ("..." if len(r["file_name"]) > 28 else ""),
            r["username"][:18],
            f"{r['country_name']} ({r['country_code'].upper()})",
            r["idc"],
            f"[{status_style}]{r['status']}[/{status_style}]",
        ]
        if deep:
            row.extend([
                str(r["followers"] if r["followers"] is not None else "-"),
                str(r["following"] if r["following"] is not None else "-"),
                str(r["videos"] if r["videos"] is not None else "-"),
            ])
        row.append(r["detail"][:38])
        table.add_row(*row)

    console.print(table)


def display_summary_breakdown(records: List[Dict[str, Any]]):
    total = len(records)
    if total == 0:
        return

    countries = collections.Counter(r["country_name"] for r in records)
    idcs = collections.Counter(r["idc"] for r in records)
    statuses = collections.Counter(r["status"] for r in records)

    country_lines = [f"[bold yellow]{c}[/bold yellow]: {cnt} ({cnt/total*100:.1f}%)" for c, cnt in countries.most_common(8)]
    idc_lines = [f"[bold cyan]{i}[/bold cyan]: {cnt} ({cnt/total*100:.1f}%)" for i, cnt in idcs.most_common(6)]
    status_lines = [f"[bold white]{s}[/bold white]: {cnt}" for s, cnt in statuses.most_common(5)]

    summary_text = (
        f"[bold white]Total Accounts Scanned:[/bold white] [bold green]{total}[/bold green]\n\n"
        f"[bold #25F4EE]Top Registration Countries:[/bold #25F4EE]\n  " + "  |  ".join(country_lines) + "\n\n"
        f"[bold #FE2C55]Target Datacenter IDCs:[/bold #FE2C55]\n  " + "  |  ".join(idc_lines) + "\n\n"
        f"[bold white]Account Health Statuses:[/bold white]\n  " + "  |  ".join(status_lines)
    )

    panel = Panel(
        summary_text,
        title="[bold white]METRIC BREAKDOWN & GEO-LOCATION DISTRIBUTION[/bold white]",
        box=box.ROUNDED,
        border_style="#25F4EE",
        padding=(1, 2),
        expand=False
    )
    console.print(panel)


def export_reports(records: List[Dict[str, Any]], export_base: str = "audit_report"):
    json_path = Path(f"{export_base}.json")
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(records, fp, indent=2, ensure_ascii=False)

    csv_path = Path(f"{export_base}.csv")
    if records:
        keys = list(records[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=keys)
            writer.writeheader()
            writer.writerows(records)

    console.print(f"\n[bold green]Report exported successfully:[/bold green]")
    console.print(f"  JSON: [white]{json_path.resolve()}[/white]")
    console.print(f"  CSV : [white]{csv_path.resolve()}[/white]")


def sort_cookies_into_country_folders(records: List[Dict[str, Any]], base_output_dir: Path):
    import shutil
    console.print(f"\n[bold #25F4EE]Organizing cookie files into country folders at:[/bold #25F4EE] {base_output_dir}")
    base_output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for r in records:
        code = r["country_code"] or "unknown"
        src = Path(r["file_path"])
        if not src.exists():
            continue
        dest_folder = base_output_dir / code
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest_file = dest_folder / src.name
        shutil.copy2(src, dest_file)
        count += 1
    console.print(f"[bold green]Copied {count} accounts into country-grouped subfolders.[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="TikTok Cookie Analyzer & Geo-Location Auditor")
    parser.add_argument("-c", "--cookies", type=str, help="Folder containing .txt or .json cookie files")
    parser.add_argument("--deep", action="store_true", help="Launch browser workers to audit live followers/following and deactivated status")
    parser.add_argument("-w", "--concurrency", type=int, default=2, help="Parallel browser instances for deep audit (default: 2)")
    parser.add_argument("--export", type=str, default="cookie_audit_report", help="Base filename to export JSON and CSV report")
    parser.add_argument("--sort", action="store_true", help="Copy cookies into country-specific folders (e.g. cookies/br/, cookies/es/)")

    args = parser.parse_args()
    print_ascii_header()

    cookie_path_str = args.cookies
    if not cookie_path_str:
        default_vault = Path(r"C:\Users\Hydra\Desktop\Alive\Tiktok")
        default_local = Path("cookies")
        if default_vault.exists():
            candidate = str(default_vault)
        elif default_local.exists():
            candidate = str(default_local)
        else:
            candidate = ""

        prompt_str = f"Enter cookies folder path (default: {candidate}): " if candidate else "Enter cookies folder path: "
        user_input = console.input(f"\n[bold #25F4EE]{prompt_str}[/bold #25F4EE]").strip()
        cookie_path_str = user_input if user_input else candidate

    folder = Path(cookie_path_str)
    if not folder.exists() or not folder.is_dir():
        console.print(f"[bold red]Error: Directory not found: {folder}[/bold red]")
        sys.exit(1)

    files = sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in (".txt", ".json")
        and not f.name.startswith(".") and not f.name.endswith(".example")
    ])

    if not files:
        console.print(f"[bold yellow]No .txt or .json cookie files found in: {folder}[/bold yellow]")
        sys.exit(0)

    console.print(f"[*] Found [bold green]{len(files)}[/bold green] cookie file(s) in: [white]{folder}[/white]")
    console.print("[*] Extracting registration countries and target IDCs from cookie headers...")

    # Fast Metadata Extraction
    records = []
    for f in files:
        rec = scan_cookie_metadata(f)
        records.append(rec)

    # Optional Deep Audit with Playwright
    if args.deep:
        console.print(f"\n[*] Starting Deep Live Audit with [bold green]{args.concurrency}[/bold green] browser worker(s)...")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--mute-audio", "--no-sandbox"]
            )
            clean_ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=clean_ua
            )

            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                futures = {executor.submit(audit_account_live, r, context): r for r in records}
                done_count = 0
                for fut in as_completed(futures):
                    done_count += 1
                    r = futures[fut]
                    pct = int(done_count / len(records) * 100)
                    if done_count % 5 == 0 or done_count == len(records):
                        console.print(f"  [dim]Audited {done_count}/{len(records)} accounts ({pct}% complete)...[/dim]")
            browser.close()

    display_results_table(records, deep=args.deep)
    display_summary_breakdown(records)
    export_reports(records, export_base=args.export)

    if args.sort:
        sort_cookies_into_country_folders(records, folder / "by_country")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Audit interrupted by user.[/yellow]")
        sys.exit(0)
