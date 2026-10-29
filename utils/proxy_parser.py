"""
Proxy parsing and normalization utility for Playwright.
Supports:
  - ip:port
  - ip:port:user:pass
  - user:pass@ip:port
  - http://ip:port
  - http://user:pass@ip:port
  - socks5://ip:port
  - socks5://user:pass@ip:port
"""
from pathlib import Path
from typing import Optional, Dict, List, Any


def parse_proxy_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single proxy string into a Playwright proxy configuration dictionary.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    scheme = "http"
    for prefix in ("socks5://", "socks4://", "http://", "https://"):
        if line.lower().startswith(prefix):
            scheme, rest = line.split("://", 1)
            line = rest
            break

    # Case 1: user:password@host:port
    if "@" in line:
        auth, host_port = line.split("@", 1)
        if ":" in auth and ":" in host_port:
            user, pwd = auth.split(":", 1)
            return {
                "server": f"{scheme}://{host_port.strip()}",
                "username": user.strip(),
                "password": pwd.strip()
            }
        return {"server": f"{scheme}://{host_port.strip()}"}

    parts = [p.strip() for p in line.split(":") if p.strip()]

    # Case 2: host:port:user:password
    if len(parts) == 4:
        host, port, user, pwd = parts
        return {
            "server": f"{scheme}://{host}:{port}",
            "username": user,
            "password": pwd
        }

    # Case 3: host:port
    if len(parts) == 2:
        host, port = parts
        return {"server": f"{scheme}://{host}:{port}"}

    # Fallback
    return {"server": f"{scheme}://{line}"}


def load_proxies(input_str: Optional[str]) -> List[Dict[str, Any]]:
    """
    Loads proxies from either a file path (e.g. proxies.txt) or a single proxy string.
    Returns an empty list if input is empty or None.
    """
    if not input_str:
        return []

    input_str = input_str.strip().strip('"').strip("'")
    if not input_str:
        return []

    path = Path(input_str)
    proxies: List[Dict[str, Any]] = []

    # If it's a file on disk
    if path.exists() and path.is_file():
        content = path.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            parsed = parse_proxy_line(line)
            if parsed:
                proxies.append(parsed)
        return proxies

    # If it's a comma/semicolon-separated list or single proxy string
    for item in input_str.replace(";", "\n").replace(",", "\n").splitlines():
        parsed = parse_proxy_line(item)
        if parsed:
            proxies.append(parsed)

    return proxies
