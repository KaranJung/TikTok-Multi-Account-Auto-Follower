"""
TikTok Multi-Account Auto-Follower Entrypoint.

Usage:
    python main.py
    python main.py --target @username --cookies ./cookies --concurrency 2 --proxy proxies.txt
"""
import sys
import time
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from bot import TikTokFollowBot, normalize_tiktok_url
from utils.cookie_parser import parse_cookie_file
from utils.proxy_parser import load_proxies
from utils.proxy_finder import collect_and_test_proxies, save_proxies_to_file
from utils.logger import (
    console,
    print_header,
    log_info,
    log_success,
    log_warning,
    log_error,
    print_summary_table
)


def get_cookie_files(path_str: str) -> list[Path]:
    """
    Return the TikTok .txt cookie files directly inside a folder or a single file.
    Filters out helper files like README, how_to, or examples.
    """
    p = Path(path_str).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {path_str}")
    if p.is_file():
        return [p]

    return [
        file_path for file_path in sorted(p.iterdir())
        if file_path.is_file()
        and file_path.suffix.lower() == ".txt"
        and not file_path.name.lower().endswith(".txt.example")
        and not file_path.name.lower().startswith("readme")
        and not file_path.name.lower().startswith("how_to")
    ]


def main():
    parser = argparse.ArgumentParser(description="TikTok Multi-Account Follow Automation via Cookies")
    parser.add_argument("-t", "--target", type=str, help="Target TikTok profile URL or @username")
    parser.add_argument("-c", "--cookies", type=str, help="Path to the folder containing .txt cookie files")
    parser.add_argument("-w", "--concurrency", type=int, default=None, help="Number of concurrent browsers to run (default: 1)")
    parser.add_argument("-p", "--proxy", type=str, default=None, help="Path to proxy file (proxies.txt) or single proxy string (optional)")
    parser.add_argument("--headless", dest="headless", action="store_true", default=None, help="Run browser in headless mode (no window)")
    parser.add_argument("--visible", dest="headless", action="store_false", help="Run browser in visible window mode")
    parser.add_argument("--delay", type=float, default=None, help="Cooldown delay (in seconds) between accounts (default: 15.0)")

    args = parser.parse_args()

    # Pre-detect proxies and cookie accounts for live status in the banner
    default_proxy_file = Path("proxies.txt")
    pre_proxies = load_proxies(str(default_proxy_file)) if default_proxy_file.exists() else []

    default_cookie_dir = Path("cookies")
    default_cookie_dir.mkdir(exist_ok=True)
    pre_accounts = []
    try:
        pre_accounts = get_cookie_files(str(default_cookie_dir))
    except Exception:
        pre_accounts = []

    # Display high-tech animated Cyber Neon HUD
    print_header(proxy_count=len(pre_proxies), account_count=len(pre_accounts), animated=True)

    # 1. Ask which folder contains the account cookie files (Interactive & Self-Healing)
    files = []
    cookie_path = args.cookies

    if cookie_path:
        try:
            files = get_cookie_files(cookie_path)
        except Exception as exc:
            log_error(f"Error accessing cookie path '{cookie_path}': {exc}")
            sys.exit(1)
        if not files:
            log_error(f"No valid .txt cookie files found in '{cookie_path}'!")
            sys.exit(1)
    else:
        while True:
            # Check default 'cookies' directory
            def_files = []
            if default_cookie_dir.exists():
                try:
                    def_files = get_cookie_files(str(default_cookie_dir))
                except Exception:
                    def_files = []

            if def_files:
                prompt_text = (
                    f"[bold #25F4EE]Cookie Vault Folder[/bold #25F4EE] "
                    f"[bold green](Press Enter for 'cookies' [{len(def_files)} accounts detected])[/bold green]: "
                )
            else:
                prompt_text = (
                    f"[bold #25F4EE]Enter cookie folder path[/bold #25F4EE] "
                    f"[dim](default: cookies)[/dim]: "
                )

            user_entry = console.input(prompt_text).strip().strip('"').strip("'")
            chosen_path = user_entry if user_entry else "cookies"

            if chosen_path.lower() in ("q", "quit", "exit"):
                log_warning("Process aborted by user.")
                sys.exit(0)

            try:
                candidate_files = get_cookie_files(chosen_path)
                if candidate_files:
                    files = candidate_files
                    log_success(f"Found [bold green]{len(files)}[/bold green] account cookie file(s) in '{chosen_path}'.")
                    break
                else:
                    abs_path = Path(chosen_path).resolve()
                    console.print(
                        f"\n[bold yellow][!] No .txt cookie files found in '{chosen_path}'![/bold yellow]\n"
                        f"[bold #25F4EE][*] Please place your exported TikTok .txt cookie files in:[/bold #25F4EE]\n"
                        f"   [bold white]{abs_path}[/bold white]\n"
                        f"[dim]   (Format: Netscape .txt, JSON array, or sessionid=... key-value tokens)[/dim]\n"
                        f"[dim]   Press Enter after adding files to re-scan, type a custom folder, or 'q' to quit.[/dim]\n"
                    )
            except Exception as exc:
                console.print(f"[bold red][-] Error reading path:[/bold red] {exc}\n")

    # 2. Accept either an @username or a full TikTok profile URL
    target_input = args.target
    while not target_input:
        target_input = console.input(
            "\n[bold #25F4EE]Target TikTok Creator[/bold #25F4EE] "
            "[dim](e.g. @username or https://www.tiktok.com/@...)[/dim]: "
        ).strip()
        if not target_input:
            log_warning("Target creator cannot be empty. Please enter @username or URL.")

    target_url = normalize_tiktok_url(target_input)
    log_info(f"Target profile normalized to: [bold green]{target_url}[/bold green]")

    # 3. Ask for Browser View mode if not passed via command line
    headless = args.headless
    if headless is None:
        console.print("\n[bold #25F4EE]Select Browser Display Mode:[/bold #25F4EE]")
        console.print("  [bold green]1.[/bold green] Visible Browser Window [dim](Default / Recommended • Reduces CAPTCHAs & lets you observe)[/dim]")
        console.print("  [bold yellow]2.[/bold yellow] Headless Mode          [dim](Silent background execution, no visible window)[/dim]")
        mode_choice = console.input("[bold #25F4EE]Enter choice [1/2][/bold #25F4EE] (default: [green]1[/green]): ").strip().lower()
        headless = mode_choice in ("2", "headless", "h", "no", "n")

    mode_label = "[yellow]Headless Mode (Background)[/yellow]" if headless else "[green]Visible Browser Window[/green]"
    log_info(f"Browser mode: {mode_label}")

    # 4. Ask for Number of Concurrent Browsers (Threads)
    concurrency = args.concurrency
    if concurrency is None:
        console.print("\n[bold #25F4EE]Concurrency (Parallel Workers):[/bold #25F4EE]")
        console.print("  [dim]Enter 1 to run sequentially, or 2+ to launch parallel browser instances.[/dim]")
        c_input = console.input(
            "[bold #25F4EE]Enter number of concurrent browsers [1-10][/bold #25F4EE] (default: [green]1[/green]): "
        ).strip()
        if c_input:
            try:
                concurrency = max(1, min(20, int(c_input)))
            except ValueError:
                concurrency = 1
        else:
            concurrency = 1

    log_info(f"Concurrency set to: [bold green]{concurrency}[/bold green] browser worker(s)")

    # 5. Proxy Configuration
    proxy_input = args.proxy
    if proxy_input is None:
        auto_proxies = load_proxies(str(default_proxy_file)) if default_proxy_file.exists() else []

        console.print("\n[bold #25F4EE]Proxy Configuration:[/bold #25F4EE]")
        if auto_proxies:
            console.print(f"  [bold green][*] Auto-detected {len(auto_proxies)} proxy/proxies from proxies.txt[/bold green]")
        console.print("  [dim]Formats supported: ip:port | ip:port:user:pass | user:pass@ip:port | socks5://...[/dim]")
        console.print("")
        console.print("  [bold green]1.[/bold green] Use proxies.txt" + (f" [dim]({len(auto_proxies)} proxies loaded)[/dim]" if auto_proxies else " [dim](empty — add proxies first)[/dim]"))
        console.print("  [bold cyan]2.[/bold cyan] Self Proxy  [dim](auto-fetch & test free proxies from the internet, then use them)[/dim]")
        console.print("  [bold yellow]3.[/bold yellow] Enter proxy manually [dim](single proxy string)[/dim]")
        console.print("  [bold white]4.[/bold white] Direct Connection [dim](no proxy)[/dim]")
        console.print("")

        proxy_choice = console.input("[bold #25F4EE]Select proxy mode [1/2/3/4][/bold #25F4EE] (default: [green]1[/green] if loaded, else [white]4[/white]): ").strip()

        if proxy_choice == "2":
            # Self Proxy: auto-collect and test free proxies
            found = collect_and_test_proxies(min_working=5, max_working=30)
            if found:
                save_proxies_to_file(found, str(default_proxy_file))
                proxies = found
                log_success(f"Self Proxy ready: {len(proxies)} working proxies loaded and saved to proxies.txt.")
            else:
                log_warning("Self Proxy: no working free proxies found. Falling back to direct connection.")
                proxies = []

        elif proxy_choice == "3":
            proxy_str = console.input(
                "[bold #25F4EE]Enter proxy[/bold #25F4EE]: "
            ).strip().strip('"').strip("'")
            proxies = load_proxies(proxy_str)
            if not proxies:
                log_warning("Could not parse proxy. Running on direct connection.")

        elif proxy_choice == "4":
            proxies = []

        else:
            # Default: use proxies.txt if it has entries, else direct
            if auto_proxies:
                proxies = auto_proxies
            else:
                log_info("proxies.txt is empty. Running on direct connection.")
                proxies = []

    else:
        proxies = load_proxies(proxy_input)

    if proxies:
        log_info(f"Loaded [bold green]{len(proxies)}[/bold green] proxy/proxies. Rotating round-robin across accounts.")
    else:
        log_info("No proxies configured. Running on direct connection.")

    # 6. Ask for Cooldown Delay if not passed via command line
    delay = args.delay
    if delay is None:
        console.print("\n[bold #25F4EE]Cooldown Delay:[/bold #25F4EE]")
        console.print("  [dim]Tip: 10-20s cooldown prevents shadow-drops by TikTok due to single-IP rate limits.[/dim]")
        delay_input = console.input(
            "[bold #25F4EE]Enter cooldown delay between follows in seconds[/bold #25F4EE] (default: [green]15.0[/green]): "
        ).strip()
        if delay_input:
            try:
                delay = max(0.0, float(delay_input))
            except ValueError:
                log_warning("Invalid delay entered; using default 15.0s.")
                delay = 15.0
        else:
            delay = 15.0

    log_info(f"Cooldown delay: [bold green]{delay}s[/bold green] between accounts")
    log_info(f"Ready to process [bold green]{len(files)}[/bold green] account(s). Starting automation...")

    # 7. Execute Bot Workers
    bot = TikTokFollowBot(headless=headless)
    results = []
    results_lock = threading.Lock()
    total_files = len(files)

    def worker_task(item):
        index, file_path = item
        account_name = file_path.name

        # Rotate proxy if proxies list is provided
        proxy = proxies[(index - 1) % len(proxies)] if proxies else None

        console.print(f"\n[bold yellow]>>> Starting Account ({index}/{total_files}): {account_name}[/bold yellow]")

        try:
            cookies = parse_cookie_file(file_path)
        except Exception as e:
            log_error(f"Failed to parse cookies from {account_name}: {e}")
            res = {
                "account": account_name,
                "status": "Invalid File",
                "action": "Skipped",
                "detail": "Failed to parse cookie format"
            }
            with results_lock:
                results.append(res)
            return res

        # Run browser automation
        res = bot.process_account(
            account_name=account_name,
            cookies=cookies,
            target_profile_url=target_url,
            proxy=proxy
        )

        # Delete expired cookie files
        if res["status"] == "Dead":
            try:
                file_path.unlink(missing_ok=True)
                log_warning(f"Deleted dead cookie file: {file_path.name}")
                res["detail"] = "Session expired; cookie file deleted"
            except OSError as exc:
                log_error(f"Could not delete {file_path.name}: {exc}")
                res["detail"] = f"Session expired; file deletion failed: {exc}"

        with results_lock:
            results.append(res)

        # Cooldown between accounts:
        # ONLY wait full cooldown if a new follow was actually performed.
        # If already following, dead, or skipped, proceed immediately without stalling!
        if res.get("action") == "Followed" and delay > 0 and index < total_files:
            log_info(f"Waiting {delay}s cooldown before next follow on this worker...")
            time.sleep(delay)
        elif res.get("action") == "Already Following":
            log_info("Account already following target; skipping cooldown to proceed immediately.")
            time.sleep(0.5)

        return res

    # Single or Multi-Worker execution
    if concurrency == 1:
        for idx, f in enumerate(files, 1):
            worker_task((idx, f))
    else:
        log_info(f"Launching pool with {concurrency} parallel browser workers...")
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            list(executor.map(worker_task, enumerate(files, 1)))

    # 8. Print Summary Table
    print_summary_table(results)
    log_success("All account automation tasks finished!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warning("\nExecution stopped by user (Ctrl+C).")
        sys.exit(0)
