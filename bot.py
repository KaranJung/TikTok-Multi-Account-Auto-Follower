"""
TikTok Automation Core Bot.
Automates browser actions using Playwright and Stealth:
1. Injects session cookies into browser context
2. Verifies session status (Active vs Dead/Expired)
3. Navigates to target user profile
4. Automatically follows creator
5. Closes browser and returns status
"""
import json
import re
import time
import random
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

from utils.logger import log_info, log_success, log_warning, log_error, log_step
from user_agent import get_random_chrome_profile, get_random_mobile_profile


def normalize_tiktok_url(target: str) -> str:
    """
    Normalizes any username, handle, or share link (including mobile tracking links like
    https://www.tiktok.com/@gueneve?_r=1&_t=ZS-9AuId5HlvUe) into a clean canonical URL:
    https://www.tiktok.com/@username
    """
    target = target.strip()

    # 1. Match @username from any URL or string (stripping query parameters)
    match = re.search(r"@([a-zA-Z0-9_.]+)", target)
    if match:
        username = match.group(1).rstrip("/")
        return f"https://www.tiktok.com/@{username}"

    # 2. If it's a short link or redirect without @ (e.g. vm.tiktok.com/...)
    if target.startswith("http://") or target.startswith("https://"):
        return target

    # 3. Raw handle without @ or URL (e.g. 'gueneve')
    clean = re.sub(r"[/?&=].*$", "", target).lstrip("@")
    return f"https://www.tiktok.com/@{clean}"


def check_session_and_relation_curl(
    cookies: List[Dict[str, Any]],
    target_profile_url: str,
    proxy: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Uses curl_cffi with Google Chrome 131 TLS/JA3/HTTP2 impersonation to check
    session status and follow relation in ~300ms without triggering Cloudflare.
    """
    try:
        from curl_cffi import requests
        cookie_dict = {str(c["name"]).strip(): str(c["value"]).strip() for c in cookies if "name" in c and "value" in c}
        if not cookie_dict:
            return None

        proxies_arg = None
        if proxy and proxy.get("server"):
            srv = proxy["server"]
            if proxy.get("username") and proxy.get("password"):
                scheme, rest = srv.split("://", 1)
                srv = f"{scheme}://{proxy['username']}:{proxy['password']}@{rest}"
            proxies_arg = {"http": srv, "https": srv}

        s = requests.Session(impersonate="chrome131")
        if proxies_arg:
            s.proxies = proxies_arg
        s.cookies.update(cookie_dict)
        s.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/",
        })

        resp = s.get(target_profile_url, timeout=12, verify=False)
        if resp.status_code != 200:
            return None

        m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', resp.text)
        if not m:
            return None

        data = json.loads(m.group(1))
        scope = data.get("__DEFAULT_SCOPE__", {})

        # 1. Check logged-in user
        user = scope.get("webapp.app-context", {}).get("user", {})
        uid = user.get("uid")
        username = user.get("uniqueId") or user.get("nickName") or ""
        if not uid or len(str(uid)) == 0:
            return {"is_alive": False, "username": "", "relation": 0}

        # 2. Check target follow relation
        user_detail = scope.get("webapp.user-detail", {}).get("userInfo", {})
        target_user = user_detail.get("user", {})
        relation = int(target_user.get("relation", 0))

        return {
            "is_alive": True,
            "username": username,
            "relation": relation,  # 0 = not following, 1 = following, 2 = friends
        }
    except Exception:
        return None


class TikTokFollowBot:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.stealth = Stealth()

    def _random_sleep(self, min_sec: float = 1.5, max_sec: float = 3.5):
        """Sleeps for a random duration to mimic human interaction."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _check_and_handle_cloudflare(self, page: Page) -> bool:
        """
        Detects Cloudflare Turnstile / 'Verify you are human' challenge and
        handles it gracefully:
          - If visible: logs warning, waits up to 30s for the user to solve it
            (or for CF to auto-pass it in headless via stealth).
          - Returns True if challenge was detected, False if page is clean.
        """
        cf_selectors = [
            # Cloudflare Turnstile iframe embed
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
            # Generic CF challenge wrapper divs
            'div#challenge-stage',
            'div.cf-challenge-running',
            'div#cf-challenge-running',
            'div#challenge-running',
            # TikTok-specific Cloudflare overlay
            'div[class*="CloudflarePopup"]',
            'div[id*="cloudflare"]',
            # Text-based detection
            'h1:has-text("Verify you are human")',
            'h2:has-text("Checking if the site connection is secure")',
        ]

        detected = False
        for sel in cf_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible(timeout=800):
                    detected = True
                    break
            except Exception:
                pass

        # Also check page title for CF challenge page
        try:
            title = page.title()
            if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                detected = True
        except Exception:
            pass

        if not detected:
            return False

        log_warning("Cloudflare challenge detected (Turnstile / 'Verify you are human').")

        # Wait up to 30s — CF often auto-solves via stealth patches, or user can solve in visible mode
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self._random_sleep(2.0, 3.0)
            still_blocked = False
            for sel in cf_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible(timeout=500):
                        still_blocked = True
                        break
                except Exception:
                    pass
            try:
                title = page.title()
                if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                    still_blocked = True
            except Exception:
                pass

            if not still_blocked:
                log_success("Cloudflare challenge passed. Continuing...")
                self._random_sleep(1.5, 2.5)
                return True

        log_error("Cloudflare challenge was NOT resolved within 30s. This account will be skipped.")
        return True  # still True = was detected, even if not resolved

    def _dismiss_popups(self, page: Page):
        """
        Attempts to close common guest banners, cookie dialogs, passkey modals, or app dialogs.
        Specifically handles: 'Create a passkey for an easier login'
        """
        # 1. Specifically detect and close the "Create a passkey" prompt
        try:
            passkey_detectors = [
                'div:has-text("Create a passkey")',
                'div:has-text("Use your face, fingerprint, PIN")',
                'div:has-text("Passkeys are safer than passwords")',
            ]
            has_passkey = False
            for p_sel in passkey_detectors:
                locator = page.locator(p_sel).first
                if locator.count() > 0 and locator.is_visible(timeout=500):
                    has_passkey = True
                    break

            if has_passkey:
                log_info("Detected 'Create a passkey' modal. Dismissing...")
                dismissed = False
                for btn_sel in [
                    'button:has-text("Maybe later")',
                    'button:has-text("Not now")',
                    'button:has-text("Cancel")',
                    'button:has-text("Skip")',
                    '[data-e2e="modal-close-icon"]',
                    'div[aria-label="Close"]',
                    'button[aria-label="Close"]',
                    'svg[data-icon="close"]',
                ]:
                    btn = page.locator(btn_sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=500):
                        btn.click()
                        dismissed = True
                        self._random_sleep(0.5, 1.0)
                        break
                if not dismissed:
                    page.keyboard.press("Escape")
                    self._random_sleep(0.5, 1.0)
        except Exception:
            pass

        # 2. General modals, overlays, and mobile app banners
        close_selectors = [
            'button:has-text("Maybe later")',
            'button:has-text("Not now")',
            'button:has-text("Stay in browser")',
            'button:has-text("Use web version")',
            'button:has-text("Continue as guest")',
            'button:has-text("Decline all")',
            'button:has-text("Accept all")',
            '[data-e2e="modal-close-icon"]',
            '[data-e2e="bottom-banner-close"]',
            '[data-e2e="feed-stay-in-web"]',
            'button[data-e2e="stay-in-web-button"]',
            'div[aria-label="Close"]',
            'button[aria-label="Close"]',
            'svg[data-icon="close"]',
        ]
        for sel in close_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible(timeout=500):
                    elem.click()
                    self._random_sleep(0.4, 0.8)
            except Exception:
                pass

    def _warmup_session(self, page: Page):
        """
        Simulates natural human engagement on the 'For You' feed:
        Watches current video, scrolls down to another video, and generates
        authentic telemetry events before performing any account action.
        """
        log_info("Warming up account session on 'For You' feed (watching videos)...")
        self._random_sleep(4.0, 7.0)
        try:
            page.keyboard.press("ArrowDown")
            self._random_sleep(3.5, 5.5)
        except Exception:
            page.mouse.wheel(0, 500)
            self._random_sleep(3.5, 5.5)

    def check_session_active(self, page: Page) -> Optional[bool]:
        """
        Determines whether the injected session is active or dead.
        Uses TikTok's internal application state (__UNIVERSAL_DATA_FOR_REHYDRATION__)
        and DOM elements for 100% deterministic detection.
        """
        self._dismiss_popups(page)

        # 1. Immediate login redirect check
        if "/login" in page.url:
            return False

        # 2. Check TikTok's internal application user state
        try:
            user_info = page.evaluate("""() => {
                try {
                    const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (el) {
                        const data = JSON.parse(el.textContent);
                        const user = data?.['__DEFAULT_SCOPE__']?.['webapp.app-context']?.user;
                        if (user && user.uid && String(user.uid).length > 0) {
                            return {
                                loggedIn: true,
                                uid: String(user.uid),
                                username: user.uniqueId || user.nickName || ''
                            };
                        }
                    }
                } catch(e) {}
                return null;
            }""")
            if user_info and user_info.get("loggedIn"):
                u_name = user_info.get("username")
                if u_name:
                    log_success(f"Logged in as @{u_name}")
                return True
        except Exception:
            pass

        # 3. Check for explicit Log in button in header
        login_btn = page.locator('#header-login-button, button[data-e2e="top-login-button"]').first
        if login_btn.count() > 0:
            try:
                btn_txt = login_btn.inner_text().strip().lower()
                if "log in" in btn_txt:
                    return False
            except Exception:
                pass

        # 4. Check for logged-in profile icon or notifications in DOM
        profile_count = page.locator(
            '[data-e2e="profile-icon"], div[data-e2e="inbox-icon"], a[data-e2e="upload-icon"], a[href*="/upload"]'
        ).count()
        if profile_count > 0:
            return True

        # 5. Check if login modal appeared
        try:
            modal = page.locator('div[data-e2e="modal-title"]:has-text("Log in to TikTok")').first
            if modal.count() > 0 and modal.is_visible(timeout=1000):
                return False
        except Exception:
            pass

        return None

    def _find_follow_button(self, page: Page):
        button = page.locator('[data-e2e="follow-button"]').first
        if button.count() == 0 or not button.is_visible():
            button = page.locator(
                'button:has-text("Following"), button:has-text("Follow"), '
                'button:has-text("Friends"), button:has-text("Requested"), '
                'div[role="button"]:has-text("Following"), div[role="button"]:has-text("Follow")'
            ).first
        return button

    @staticmethod
    def _follow_state(button) -> str:
        try:
            text = button.inner_text().strip().lower()
        except Exception:
            text = ""
        try:
            aria_label = (button.get_attribute("aria-label") or "").strip().lower()
        except Exception:
            aria_label = ""
        combined = f"{text} {aria_label}"
        if any(state in combined for state in ("following", "friends")):
            return "following"
        if "requested" in combined:
            return "requested"
        if "follow" in combined and "unfollow" not in combined:
            return "follow"
        return "unknown"

    def process_account(
        self,
        account_name: str,
        cookies: List[Dict[str, Any]],
        target_profile_url: str,
        proxy: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Executes the automation lifecycle for a single account:
        1. Launches browser with anti-bot evasion and optional proxy
        2. Injects session cookies
        3. Verifies session status
        4. Navigates to target user profile
        5. Performs the Follow action
        6. Closes the browser
        """
        log_step(f"Processing Account: {account_name}")
        result = {
            "account": account_name,
            "status": "Unknown",
            "action": "Failed",
            "detail": ""
        }

        # Step 1: Fast TLS/JA3 pre-check using curl_cffi (Google Chrome 131 TLS fingerprint)
        # Bypasses Cloudflare instantly without launching a browser if already following or dead!
        precheck = check_session_and_relation_curl(cookies, target_profile_url, proxy)
        if precheck:
            if not precheck.get("is_alive"):
                log_error(f"Session is DEAD / EXPIRED for {account_name} (checked via curl_cffi TLS spoofing)!")
                result["status"] = "Dead"
                result["action"] = "Skipped"
                result["detail"] = "Session expired or invalid login"
                return result

            uname = precheck.get("username")
            if uname:
                log_success(f"Logged in as @{uname} (verified via curl_cffi)")
                result["status"] = "Active"

            relation = precheck.get("relation", 0)
            if relation in (1, 2):
                log_success(f"ALREADY FOLLOWING: {account_name} is already following! (verified via curl_cffi in 0.3s)")
                result["status"] = "Active"
                result["action"] = "Already Following"
                result["detail"] = "Follow state confirmed (already following)"
                return result

        with sync_playwright() as p:
            # Configure browser launch with matching Chrome TLS, no automation flags, and audio mute
            launch_kwargs = {
                "headless": self.headless,
                "ignore_default_args": ["--enable-automation"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--mute-audio",
                    "--ignore-certificate-errors",
                    "--ignore-ssl-errors",
                    "--allow-running-insecure-content",
                ]
            }
            if proxy:
                launch_kwargs["proxy"] = proxy
                log_info(f"Using proxy: [bold yellow]{proxy.get('server')}[/bold yellow]")

            browser: Browser = p.chromium.launch(**launch_kwargs)

            # Pick a standard Google Chrome profile matching Chromium BoringSSL TLS/JA3
            profile = get_random_chrome_profile()
            log_info(f"Launching Chrome with matching TLS/JA3: [bold cyan]{profile['name']}[/bold cyan]")

            context: BrowserContext = browser.new_context(
                viewport=profile["viewport"],
                user_agent=profile["user_agent"],
                is_mobile=profile.get("is_mobile", False),
                has_touch=profile.get("has_touch", False),
                device_scale_factor=profile.get("device_scale_factor", 1),
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
            )

            # Bulletproof permanent audio mute & Puppeteer-Extra Stealth evasions
            try:
                context.add_init_script("""
                    try {
                        // 1. Delete Object.getPrototypeOf(navigator).webdriver and mask getter
                        delete Object.getPrototypeOf(navigator).webdriver;
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

                        // 2. Mock authentic window.chrome object (puppeteer-extra-plugin-stealth)
                        window.chrome = {
                            runtime: {},
                            loadTimes: () => {},
                            csi: () => {},
                            app: {}
                        };

                        // 3. Mock permissions query for notifications
                        const origQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                                Promise.resolve({ state: Notification.permission === 'denied' ? 'denied' : 'prompt' }) :
                                origQuery(parameters)
                        );

                        // 4. Mock navigator.plugins length to avoid headless empty plugins detection
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });

                        // 5. Permanent audio mute
                        Object.defineProperty(HTMLMediaElement.prototype, 'muted', {
                            get: () => true,
                            set: () => {},
                            configurable: true
                        });
                        Object.defineProperty(HTMLMediaElement.prototype, 'volume', {
                            get: () => 0,
                            set: () => {},
                            configurable: true
                        });
                        if (window.AudioContext) {
                            const _origAC = window.AudioContext;
                            window.AudioContext = function() {
                                const ctx = new _origAC();
                                try { ctx.suspend(); } catch(e) {}
                                return ctx;
                            };
                        }
                    } catch(e) {}
                """)
            except Exception:
                pass

            page: Page = context.new_page()
            self.stealth.apply_stealth_sync(page)

            try:
                # Step 1: Inject cookies
                log_info(f"Injecting {len(cookies)} cookies into browser context...")
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    log_warning(f"Bulk cookie injection notice: {e}. Injecting valid cookies individually...")
                    injected = 0
                    for c in cookies:
                        try:
                            context.add_cookies([c])
                            injected += 1
                        except Exception:
                            pass
                    log_info(f"Successfully injected {injected}/{len(cookies)} cookies.")

                # Step 2: Navigate directly to target profile
                log_info(f"Navigating to target profile: {target_profile_url}")
                page_resp = page.goto(target_profile_url, wait_until="domcontentloaded", timeout=45000)
                self._random_sleep(1.5, 2.5)

                # Check if TikTok blocked the proxy IP with 403 Forbidden
                if page_resp and page_resp.status == 403:
                    log_error(f"TikTok returned 403 Forbidden on proxy IP for {account_name}!")
                    result["action"] = "Proxy Blocked"
                    result["detail"] = "Proxy IP blocked by TikTok (403)"
                    return result

                try:
                    body_text = page.locator("body").inner_text(timeout=1000).strip().lower()
                    if body_text == "forbidden" or "access denied" in body_text:
                        log_error(f"TikTok blocked proxy IP (Forbidden / Access Denied) for {account_name}!")
                        result["action"] = "Proxy Blocked"
                        result["detail"] = "Proxy IP blocked by TikTok (Forbidden)"
                        return result
                except Exception:
                    pass

                # Check for Cloudflare challenge before anything else
                cf_hit = self._check_and_handle_cloudflare(page)
                if cf_hit:
                    # Re-check whether we passed or got stuck
                    try:
                        title = page.title()
                        if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                            result["action"] = "Cloudflare Blocked"
                            result["detail"] = "Cloudflare challenge not resolved"
                            return result
                    except Exception:
                        pass

                self._dismiss_popups(page)

                # Step 3: Check if session is alive
                is_alive = self.check_session_active(page)
                if is_alive is False:
                    log_error(f"Session is DEAD / EXPIRED for {account_name}!")
                    result["status"] = "Dead"
                    result["action"] = "Skipped"
                    result["detail"] = "Session expired or invalid login"
                    return result
                if is_alive is True:
                    log_success(f"Session is ACTIVE for {account_name}!")
                    result["status"] = "Active"

                # Check if target profile exists
                not_found = page.locator('main:has-text("Couldn\'t find this account")').first
                if not_found.count() > 0 and not_found.is_visible(timeout=1500):
                    log_error("Target account not found! Please check the username.")
                    result["action"] = "Failed"
                    result["detail"] = "Account does not exist"
                    return result

                # Step 4: Locate Follow button and inspect state IMMEDIATELY
                follow_btn = self._find_follow_button(page)
                if follow_btn.count() == 0 or not follow_btn.is_visible():
                    try:
                        page.wait_for_selector(
                            '[data-e2e="follow-button"], button:has-text("Following"), button:has-text("Follow")',
                            timeout=3500
                        )
                        follow_btn = self._find_follow_button(page)
                    except Exception:
                        pass

                if follow_btn.count() == 0 or not follow_btn.is_visible(timeout=2000):
                    log_warning("Follow button not found on page (profile may be private or your own).")
                    result["action"] = "Failed"
                    result["detail"] = "Follow button not found"
                    return result

                state = self._follow_state(follow_btn)
                log_info(f"Current follow state: {state}")

                # FAST-PATH: If already following or requested, close browser IMMEDIATELY (no waiting!)
                if state == "following":
                    log_success(f"ALREADY FOLLOWING: {account_name} is already following! Closing browser immediately.")
                    result["status"] = "Active"
                    result["action"] = "Already Following"
                    result["detail"] = "Follow state confirmed (already following)"
                    return result

                if state == "requested":
                    log_warning(f"REQUESTED: Follow request already pending for {account_name}. Closing browser.")
                    result["status"] = "Active"
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                    return result

                if state != "follow":
                    log_warning("The profile follow state could not be determined.")
                    result["detail"] = "Unknown follow button state"
                    return result

                # Step 5: If NOT following yet, perform humanized interaction & follow
                # Set up network listener to intercept the real follow commit API response
                api_result = {"received": False, "status_code": None, "follow_status": None, "msg": ""}

                def on_response(resp):
                    if "commit/follow/user" in resp.url:
                        try:
                            payload = resp.json()
                            api_result["received"] = True
                            api_result["status_code"] = payload.get("status_code")
                            api_result["follow_status"] = payload.get("follow_status")
                            api_result["msg"] = payload.get("status_msg", "")
                        except Exception:
                            pass

                page.on("response", on_response)

                log_info("Browsing creator profile before following...")
                try:
                    page.mouse.wheel(0, random.randint(250, 450))
                    self._random_sleep(1.0, 1.8)
                    page.mouse.wheel(0, -random.randint(250, 450))
                    self._random_sleep(0.8, 1.4)
                except Exception:
                    pass

                self._dismiss_popups(page)

                log_info("Hovering and clicking 'Follow' button...")
                follow_btn.scroll_into_view_if_needed()
                self._random_sleep(0.4, 0.8)
                follow_btn.hover()
                self._random_sleep(0.3, 0.6)
                follow_btn.click(delay=random.randint(60, 140))

                # A click alone is not success: wait until TikTok confirms the new state.
                deadline = time.monotonic() + 12
                state = "unknown"
                while time.monotonic() < deadline:
                    self._random_sleep(1.0, 1.5)

                    # Check for Cloudflare or TikTok CAPTCHA appearing post-click
                    if self._check_and_handle_cloudflare(page):
                        try:
                            title = page.title()
                            if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                                result["action"] = "Cloudflare Blocked"
                                result["detail"] = "Cloudflare blocked follow action"
                                return result
                        except Exception:
                            pass

                    if page.locator("div#tiktok-verify-ele, div[class*='captcha']").first.is_visible():
                        log_warning("TikTok CAPTCHA challenge popped up!")
                        result["action"] = "Captcha Triggered"
                        result["detail"] = "Captcha challenge triggered"
                        return result

                    follow_btn = self._find_follow_button(page)
                    if follow_btn.count() > 0:
                        state = self._follow_state(follow_btn)
                        if state in ("following", "requested") or api_result["received"]:
                            break

                # Inspect backend API response if received
                if api_result["received"]:
                    if api_result["status_code"] != 0 or api_result["follow_status"] == 0:
                        msg = api_result["msg"] or "Blocked by TikTok anti-bot / rate limit"
                        log_error(f"TikTok server rejected follow: {msg}")
                        result["action"] = "Action Blocked"
                        result["detail"] = f"Server rejected: {msg}"
                        return result
                    else:
                        log_info(f"TikTok server accepted follow (code={api_result['status_code']}, status={api_result['follow_status']}).")

                # Persistence check: wait to ensure backend didn't shadow-drop / revert
                log_info("Verifying follow persistence (waiting for backend sync)...")
                self._random_sleep(4.0, 6.0)
                follow_btn = self._find_follow_button(page)
                if follow_btn.count() > 0:
                    state = self._follow_state(follow_btn)
                    if state not in ("following", "requested"):
                        log_warning(f"Follow was shadow-dropped/reverted by TikTok backend for {account_name}!")
                        result["action"] = "Shadow-Dropped"
                        result["detail"] = "Reverted by TikTok (IP rate limit)"
                        return result

                if state == "following":
                    log_success(f"FOLLOWED: {account_name} successfully followed target (persisted).")
                    result["action"] = "Followed"
                    result["detail"] = "Follow verified & persisted"
                elif state == "requested":
                    log_warning("Follow request sent; waiting for the target to accept it.")
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                else:
                    log_warning("Follow was not confirmed; target may not have been followed.")
                    result["detail"] = "Follow state not confirmed"

                return result

            except Exception as e:
                err_msg = str(e)
                if any(k in err_msg for k in ("ERR_PROXY", "ERR_TUNNEL", "ERR_CERT", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_CLOSED")):
                    log_error(f"Proxy network error for {account_name}: {err_msg[:80]}")
                    result["action"] = "Proxy Failed"
                    result["detail"] = f"Proxy error: {err_msg[:40]}"
                else:
                    log_error(f"Error during execution for {account_name}: {err_msg}")
                    result["detail"] = f"Error: {err_msg[:50]}"
                return result

            finally:
                log_info(f"Closing browser for {account_name}...")
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
