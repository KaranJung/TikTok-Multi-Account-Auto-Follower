"""
Multi-format cookie parser for TikTok sessions.
Supports:
1. JSON export format (Cookie-Editor, EditThisCookie)
2. Netscape tab-delimited cookies.txt format (including #HttpOnly_ prefixes)
3. Header / Key-Value format (sessionid=xxxx; sid_guard=yyyy)
4. Raw single session ID token string
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any


def normalize_playwright_cookie(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures a cookie dictionary strictly conforms to Playwright and Chromium requirements:
    - If cookie starts with '__Host-', Playwright requires ONLY 'url', no 'domain' or 'path'.
    - If cookie has 'sameSite' == 'None', 'secure' MUST be True.
    - Preserves httpOnly and integer timestamps.
    """
    name = str(item.get("name", "")).strip()
    value = str(item.get("value", "")).strip()
    if not name:
        return {}

    cookie: Dict[str, Any] = {
        "name": name,
        "value": value,
    }

    # Handle __Host- prefix RFC 6265bis rule
    if name.startswith("__Host-"):
        cookie["url"] = "https://www.tiktok.com"
        cookie["secure"] = True
    else:
        raw_domain = str(item.get("domain", "")).strip()
        if raw_domain.startswith("#HttpOnly_"):
            raw_domain = raw_domain[len("#HttpOnly_"):]
        if "tiktok.com" in raw_domain:
            if raw_domain.startswith("."):
                cookie["domain"] = raw_domain
            else:
                cookie["domain"] = f".{raw_domain}"
        else:
            cookie["domain"] = ".tiktok.com"
        cookie["path"] = str(item.get("path", "/")) or "/"

    # Secure attribute
    if "secure" in item:
        cookie["secure"] = bool(item["secure"])
    else:
        cookie["secure"] = True

    if name.startswith("__Secure-") or name.startswith("__Host-"):
        cookie["secure"] = True

    # HttpOnly attribute
    if "httpOnly" in item:
        cookie["httpOnly"] = bool(item["httpOnly"])

    # sameSite attribute: Chromium requires secure=True if sameSite is None
    if "sameSite" in item and item["sameSite"]:
        raw_ss = str(item["sameSite"]).strip().capitalize()
        if raw_ss in ("Strict", "Lax", "None"):
            cookie["sameSite"] = raw_ss
            if raw_ss == "None":
                cookie["secure"] = True
        elif raw_ss.lower() in ("no_restriction", "unspecified"):
            cookie["sameSite"] = "None"
            cookie["secure"] = True

    # Expiration timestamp check
    exp_val = item.get("expirationDate") or item.get("expires")
    if exp_val is not None:
        try:
            exp = float(exp_val)
            if exp > 0:
                cookie["expires"] = int(exp)
        except (ValueError, TypeError):
            pass

    return cookie


def parse_cookie_file(file_path: str | Path) -> List[Dict[str, Any]]:
    """
    Parses a cookie file into Playwright-compatible cookie dictionaries.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Cookie file not found: {file_path}")

    content = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not content:
        raise ValueError(f"Cookie file is empty: {file_path}")

    cookies: List[Dict[str, Any]] = []

    # 1. Try parsing as JSON array
    if (content.startswith("[") and content.endswith("]")) or (content.startswith("{") and content.endswith("}")):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                for raw_c in data:
                    if isinstance(raw_c, dict) and "name" in raw_c and "value" in raw_c:
                        norm = normalize_playwright_cookie(raw_c)
                        if norm:
                            cookies.append(norm)
                if cookies:
                    return cookies
        except Exception:
            pass

    # 2. Try Netscape format (tab-separated columns: domain flag path secure expiry name value)
    is_netscape = False
    netscape_cookies = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_httponly = False
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            is_httponly = True
        elif line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) >= 7:
            is_netscape = True
            domain, flag, path_val, secure, expiry, name, value = parts[:7]
            norm = normalize_playwright_cookie({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_val,
                "secure": secure.upper() == "TRUE",
                "httpOnly": is_httponly,
                "expires": expiry
            })
            if norm:
                netscape_cookies.append(norm)

    if is_netscape and netscape_cookies:
        return netscape_cookies

    # 3. Try key-value header or newline format (e.g. sessionid=xxxx; sid_guard=yyyy)
    if "=" in content:
        tokens = re.split(r"[;\n]", content)
        for token in tokens:
            token = token.strip()
            if not token or token.startswith("#"):
                continue
            if "=" in token:
                k, v = token.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    norm = normalize_playwright_cookie({
                        "name": k,
                        "value": v,
                        "domain": ".tiktok.com",
                        "path": "/",
                        "secure": True
                    })
                    if norm:
                        cookies.append(norm)
        if cookies:
            return cookies

    # 4. Fallback: Raw session ID string (single alphanumeric token)
    single_token = content.strip().strip('"').strip("'")
    if len(single_token) > 15 and " " not in single_token:
        norm = normalize_playwright_cookie({
            "name": "sessionid",
            "value": single_token,
            "domain": ".tiktok.com",
            "path": "/",
            "secure": True
        })
        if norm:
            return [norm]

    raise ValueError(
        f"Unable to recognize cookie format in {path.name}. "
        "Please provide a JSON cookie array, Netscape cookies.txt, or key=value header format."
    )
