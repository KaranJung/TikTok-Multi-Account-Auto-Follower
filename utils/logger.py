"""
Terminal logger compatible with Windows cp1252 and UTF-8 consoles.
Provides animated cyberpunk headers, live status diagnostics, and rich execution tables.
No emojis used to ensure 100% stable terminal rendering without buffer reflow issues.
"""
import sys
import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

# Ensure UTF-8 output and VT100 ANSI sequences on Windows consoles
if sys.platform == "win32":
    os.system("")  # Activates Windows VT100 / Virtual Terminal Processing
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.text import Text
from rich import box

# Console instance configured for modern ANSI/UTF-8 output
console = Console(highlight=False, legacy_windows=False)


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log_info(msg: str):
    console.print(f"[dim cyan][{get_timestamp()}][/dim cyan] [bold #25F4EE][*][/bold #25F4EE] {msg}")


def log_success(msg: str):
    console.print(f"[dim cyan][{get_timestamp()}][/dim cyan] [bold green][+][/bold green] [green]{msg}[/green]")


def log_warning(msg: str):
    console.print(f"[dim cyan][{get_timestamp()}][/dim cyan] [bold yellow][!][/bold yellow] [yellow]{msg}[/yellow]")


def log_error(msg: str):
    console.print(f"[dim cyan][{get_timestamp()}][/dim cyan] [bold red][-][/bold red] [red]{msg}[/red]")


def log_step(title: str):
    console.print(
        f"\n[bold #25F4EE]╭───[/bold #25F4EE] [bold white on #FE2C55] {title} [/bold white on #FE2C55] [bold #25F4EE]───────────────────────────[/bold #25F4EE]"
    )


def print_header(proxy_count: int = 0, account_count: int = 0, animated: bool = True):
    """
    Renders an animated high-tech neon header with live system statistics and diagnostics.
    """
    # ASCII Art Logo (TikTok Cyber Neon)
    logo_lines = [
        ("  ████████╗██╗██╗  ██╗", "████████╗ ██████╗ ██╗  ██╗"),
        ("  ╚══██╔══╝██║██║ ██╔╝", "╚══██╔══╝██╔═══██╗██║ ██╔╝"),
        ("     ██║   ██║█████╔╝ ", "   ██║   ██║   ██║█████╔╝ "),
        ("     ██║   ██║██╔═██╗ ", "   ██║   ██║   ██║██╔═██╗ "),
        ("     ██║   ██║██║  ██╗", "   ██║   ╚██████╔╝██║  ██╗"),
        ("     ╚═╝   ╚═╝╚═╝  ╚═╝", "   ╚═╝    ╚═════╝ ╚═╝  ╚═╝"),
    ]

    rendered_logo = []
    for left, right in logo_lines:
        line_text = Text()
        line_text.append(left, style="bold #FE2C55")
        line_text.append(right, style="bold #25F4EE")
        rendered_logo.append(line_text)

    # Subtitle and feature line
    sub = Text.from_markup(
        "[bold white]MULTI-ACCOUNT AUTO-FOLLOWER[/bold white] [bold #FE2C55]•[/bold #FE2C55] [bold #25F4EE]NATIVE BROWSER[/bold #25F4EE]\n"
        "[dim]Cookie Sessions  •  Native Browser Identity  •  Manual Security Checks[/dim]"
    )

    # Live System Status Matrix
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold #FE2C55", justify="left")
    grid.add_column(style="white", justify="left")
    grid.add_column(style="bold #25F4EE", justify="left")
    grid.add_column(style="white", justify="left")

    p_badge = (
        f"[bold green]{proxy_count} saved (proxies.txt)[/bold green]"
        if proxy_count > 0
        else "[yellow]Direct Network[/yellow]"
    )
    a_badge = (
        f"[bold green]{account_count} account(s) ready[/bold green]"
        if account_count > 0
        else "[yellow]None detected (./cookies)[/yellow]"
    )

    grid.add_row("CREATOR  :", "[bold white]@hydra_X001[/bold white]", "TELEGRAM :", "[bold yellow]https://t.me/hydrax001[/bold yellow]")
    grid.add_row("IDENTITY :", "[green]Native browser defaults[/green]", "PROXIES  :", p_badge)
    grid.add_row("ENGINE   :", "[green]Playwright Chromium[/green]", "SESSIONS :", a_badge)

    panel_content = Group(
        Text(""),
        Group(*[Align.center(line) for line in rendered_logo]),
        Text(""),
        Align.center(sub),
        Text(""),
        Align.center(grid),
        Text("")
    )

    panel = Panel(
        panel_content,
        box=box.ROUNDED,
        border_style="#25F4EE",
        subtitle="[bold #FE2C55]-- HYDRA ULTIMATE AUTOMATION --[/bold #FE2C55]",
        subtitle_align="center",
        padding=(0, 2),
        expand=False,
    )

    if animated:
        # Step 1: Animate banner entrance
        time.sleep(0.05)
        console.print(panel)

        # Step 2: Animated rapid system diagnostics HUD
        time.sleep(0.08)
        diag_steps = [
            ("[*]", "[bold #25F4EE]Native UA / Client Hints[/bold #25F4EE]", "[bold green]DEFAULT[/bold green]"),
            ("[*]", "[bold #FE2C55]Security Challenge Handling[/bold #FE2C55]", "[bold yellow]MANUAL[/bold yellow]"),
            ("[*]", "[bold white]Session Vault & Proxy Router[/bold white]", "[bold green]ACTIVE[/bold green]"),
        ]

        for tag, name, status in diag_steps:
            console.print(
                f"  {tag} [white]System Diagnostics:[/white] {name}  [dim]...[/dim] [{status}]"
            )
            time.sleep(0.05)
        console.print("")
    else:
        console.print(panel)
        console.print("")


def print_summary_table(results: List[Dict[str, Any]]):
    """
    Renders an elegant summary table of all account runs.
    """
    table = Table(
        title="[bold white]=== EXECUTION SUMMARY REPORT ===[/bold white]",
        box=box.ROUNDED,
        border_style="#25F4EE",
        header_style="bold #FE2C55",
        title_style="bold magenta",
        expand=False,
    )
    table.add_column("Account File", style="bold white")
    table.add_column("Session Status", justify="center")
    table.add_column("Follow Action", justify="center")
    table.add_column("Details", style="dim white")

    for r in results:
        status_color = "green" if r["status"] == "Active" else "yellow" if r["status"] == "Unknown" else "red"
        action_color = (
            "green"
            if r["action"] in ["Followed", "Already Following"]
            else "yellow"
            if r["action"] in ["Skipped", "Captcha Triggered", "Requested", "Cloudflare Blocked", "Proxy Failed",
                                           "Rate Limited", "Access Blocked", "Verification Inconclusive"]
            else "red"
        )

        table.add_row(
            f"{r['account']}",
            f"[{status_color}][{r['status']}][/{status_color}]",
            f"[{action_color}][{r['action']}][/{action_color}]",
            r["detail"],
        )

    console.print("\n")
    console.print(table)
    console.print("")
