"""
Standard Google Chrome User-Agents & Device Profiles.
Matches Chromium BoringSSL TLS/JA3/JA4 Fingerprint to prevent Cloudflare bot flagging.
"""
import random
from typing import Dict, Any, List

# -----------------------------------------------------------------------------
# Standard Google Chrome (Desktop Windows 10/11 & Android Mobile)
# Matches Playwright Chromium's TLS ClientHello BoringSSL handshake byte-for-byte.
# -----------------------------------------------------------------------------
CHROME_DEVICE_PROFILES: List[Dict[str, Any]] = [
    # --- Windows 10 / 11 Desktop (Google Chrome 128 - 131) ---
    {
        "name": "Windows Desktop (Chrome 131)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "viewport": {"width": 1536, "height": 864},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
    },
    {
        "name": "Windows Desktop (Chrome 130)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.117 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
    },
    {
        "name": "Windows Desktop (Chrome 129)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.101 Safari/537.36",
        "viewport": {"width": 1440, "height": 900},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
    },
    {
        "name": "Windows Desktop (Chrome 128)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.138 Safari/537.36",
        "viewport": {"width": 1366, "height": 768},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
    },

    # --- Android Mobile Flagships (Google Chrome 128 - 131) ---
    {
        "name": "Samsung Galaxy S24 Ultra (Android 14 Chrome)",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "platform": "Linux armv8l",
    },
    {
        "name": "Samsung Galaxy S24 (Android 14 Chrome)",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
        "viewport": {"width": 384, "height": 832},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "platform": "Linux armv8l",
    },
    {
        "name": "Google Pixel 9 Pro (Android 15 Chrome)",
        "user_agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "platform": "Linux armv8l",
    },
    {
        "name": "Google Pixel 8 Pro (Android 14 Chrome)",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "platform": "Linux armv8l",
    },
    {
        "name": "Xiaomi 14 Ultra (Android 14 Chrome)",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; 24030PN60G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "platform": "Linux armv8l",
    },
]

ALL_PHONE_USER_AGENTS = [p["user_agent"] for p in CHROME_DEVICE_PROFILES]


def get_random_chrome_profile() -> Dict[str, Any]:
    """
    Returns a randomized Google Chrome profile that strictly matches Chromium BoringSSL TLS/JA3.
    """
    return random.choice(CHROME_DEVICE_PROFILES)


# Backwards compatibility aliases
get_random_mobile_profile = get_random_chrome_profile
get_random_apple_profile = get_random_chrome_profile


def get_random_user_agent() -> str:
    """Returns a random Google Chrome user-agent string."""
    return random.choice(ALL_PHONE_USER_AGENTS)


if __name__ == "__main__":
    print(f"[+] Loaded {len(CHROME_DEVICE_PROFILES)} standard Google Chrome TLS/JA3-matched profiles!")
    for idx, p in enumerate(CHROME_DEVICE_PROFILES, 1):
        print(f"  {idx}. {p['name']} -> {p['viewport']['width']}x{p['viewport']['height']}")
    sample = get_random_chrome_profile()
    print("\n[+] Sample Chrome Profile:")
    print(f"    Name:       {sample['name']}")
    print(f"    User-Agent: {sample['user_agent']}")
