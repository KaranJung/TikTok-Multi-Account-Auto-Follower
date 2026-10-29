"""
Standard Google Chrome Desktop User-Agents & Device Profiles.
Strictly uses Desktop Windows Chrome profiles so navigator.platform, Sec-CH-UA headers,
and Chromium BoringSSL TLS/JA3 fingerprints match 100% (avoiding Android-on-Desktop mismatch).
No emojis used.
"""
import random
from typing import Dict, Any, List

CHROME_DEVICE_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "Windows Desktop (Chrome 131 - 1080p)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "name": "Windows Desktop (Chrome 131 - 1536x864)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "viewport": {"width": 1536, "height": 864},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "name": "Windows Desktop (Chrome 130 - 1440x900)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "viewport": {"width": 1440, "height": 900},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
        "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    },
    {
        "name": "Windows Desktop (Chrome 129 - 1366x768)",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "viewport": {"width": 1366, "height": 768},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
        "platform": "Win32",
        "sec_ch_ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    },
]

ALL_PHONE_USER_AGENTS = [p["user_agent"] for p in CHROME_DEVICE_PROFILES]


def get_random_chrome_profile() -> Dict[str, Any]:
    """
    Returns a randomized Desktop Google Chrome profile with aligned Client Hints and platform.
    """
    return random.choice(CHROME_DEVICE_PROFILES)


# Backwards compatibility aliases
get_random_mobile_profile = get_random_chrome_profile
get_random_apple_profile = get_random_chrome_profile


def get_random_user_agent() -> str:
    """Returns a random Google Chrome user-agent string."""
    return random.choice(ALL_PHONE_USER_AGENTS)


if __name__ == "__main__":
    print(f"Loaded {len(CHROME_DEVICE_PROFILES)} standard Google Chrome TLS/JA3-matched profiles")
    for idx, p in enumerate(CHROME_DEVICE_PROFILES, 1):
        print(f"  {idx}. {p['name']} -> {p['viewport']['width']}x{p['viewport']['height']}")
    sample = get_random_chrome_profile()
    print("\nSample Chrome Profile:")
    print(f"    Name:       {sample['name']}")
    print(f"    User-Agent: {sample['user_agent']}")
