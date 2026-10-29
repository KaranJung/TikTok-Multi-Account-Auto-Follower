"""
Standard Google Chrome Desktop Device Profiles.
Keeps Playwright Chromium's native desktop User-Agent (user_agent: None)
so HTTP User-Agent, Sec-CH-UA headers, navigator.platform, and TLS fingerprint match 100% without conflicts.
No emojis used.
"""
import random
from typing import Dict, Any, List, Optional

CHROME_DEVICE_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "Native Desktop Chromium (1920x1080)",
        "user_agent": None,
        "viewport": {"width": 1920, "height": 1080},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
    {
        "name": "Native Desktop Chromium (1536x864)",
        "user_agent": None,
        "viewport": {"width": 1536, "height": 864},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
    {
        "name": "Native Desktop Chromium (1440x900)",
        "user_agent": None,
        "viewport": {"width": 1440, "height": 900},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
    {
        "name": "Native Desktop Chromium (1366x768)",
        "user_agent": None,
        "viewport": {"width": 1366, "height": 768},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
]

ALL_PHONE_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
]


def get_random_chrome_profile() -> Dict[str, Any]:
    """
    Returns a Desktop Chromium profile that keeps user_agent as None to preserve
    Playwright Chromium's 100% native client hints, navigator.platform, and TLS fingerprint.
    """
    return random.choice(CHROME_DEVICE_PROFILES)


# Backwards compatibility aliases
get_random_mobile_profile = get_random_chrome_profile
get_random_apple_profile = get_random_chrome_profile


def get_random_user_agent() -> Optional[str]:
    """Returns None to use native Chromium user agent, or standard Chrome UA string."""
    return None


if __name__ == "__main__":
    print(f"Loaded {len(CHROME_DEVICE_PROFILES)} native Google Chrome profiles")
    for idx, p in enumerate(CHROME_DEVICE_PROFILES, 1):
        print(f"  {idx}. {p['name']} -> {p['viewport']['width']}x{p['viewport']['height']}")
    sample = get_random_chrome_profile()
    print("\nSample Chrome Profile:")
    print(f"    Name:       {sample['name']}")
    print(f"    User-Agent: {sample['user_agent']} (Native Playwright Chromium)")
