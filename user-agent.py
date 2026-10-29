"""
User-Agent module alias for user_agent.py (Standard Google Chrome TLS/JA3).
Allows executing 'python user-agent.py' or importing directly.
"""
from user_agent import (
    CHROME_DEVICE_PROFILES,
    ALL_PHONE_USER_AGENTS,
    get_random_chrome_profile,
    get_random_mobile_profile,
    get_random_user_agent
)

__all__ = [
    "CHROME_DEVICE_PROFILES",
    "ALL_PHONE_USER_AGENTS",
    "get_random_chrome_profile",
    "get_random_mobile_profile",
    "get_random_user_agent"
]

if __name__ == "__main__":
    print(f"[+] Loaded {len(CHROME_DEVICE_PROFILES)} standard Google Chrome TLS/JA3-matched profiles!")
    for idx, p in enumerate(CHROME_DEVICE_PROFILES, 1):
        print(f"  {idx}. {p['name']}")
    sample = get_random_chrome_profile()
    print("\n[+] Sample Selected Chrome Profile:")
    print(f"    Name: {sample['name']}")
    print(f"    UA:   {sample['user_agent']}")
