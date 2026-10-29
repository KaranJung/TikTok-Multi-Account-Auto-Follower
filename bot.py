"""
TikTok Automation Core Bot.
Anti-Ghost & Native Stealth Follow System:
1. Native Chromium Environment:
   Relies on Chromium's native --disable-blink-features=AutomationControlled and --mute-audio flags.
   Zero init_script monkey-patches so navigator.plugins, navigator.webdriver, and AudioContext remain 100% native.
2. Aligned User-Agent & Client Hints:
   Keeps Playwright Chromium's native desktop User-Agent (user_agent: None) so HTTP User-Agent,
   Sec-CH-UA headers, navigator.platform, and TLS fingerprint match without conflicts.
3. Automatic msToken Session Warmup:
   If a cookie file doesn't have an active msToken, warms up on https://www.tiktok.com/ first
   so webmssdk.js initializes valid security tokens before visiting the target profile.
4. Real Server Verification After Clicking Follow:
   Waits specifically for the /api/commit/follow/user/ network response, waits 5 seconds,
   and reloads the profile page (page.reload()) to verify both the server hydration state
   (userInfo.user.relation in 1, 2) and the reloaded button state.
5. Cloudflare detection & proxy error isolation.
No emojis used.
"""
import json
import re
import time
import random
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from utils.logger import log_info, log_success, log_warning, log_error, log_step
from user_agent import get_random_chrome_profile


def normalize_tiktok_url(target: str) -> str:
    target = target.strip()
    match = re.search(r"@([a-zA-Z0-9_.]+)", target)
    if match:
        username = match.group(1).rstrip("/")
        return f"https://www.tiktok.com/@{username}"
    if target.startswith("http://") or target.startswith("https://"):
        return target
    clean = re.sub(r"[/?&=].*$", "", target).lstrip("@")
    return f"https://www.tiktok.com/@{clean}"


class TikTokFollowBot:
    def __init__(self, headless: bool = False):
        self.headless = headless

    def _random_sleep(self, min_sec: float = 1.5, max_sec: float = 3.5):
        time.sleep(random.uniform(min_sec, max_sec))

    def _check_and_handle_cloudflare(self, page: Page) -> bool:
        cf_selectors = [
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
            'div#challenge-stage',
            'div.cf-challenge-running',
            'div#cf-challenge-running',
            'div#challenge-running',
            'div[class*="CloudflarePopup"]',
            'div[id*="cloudflare"]',
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

        try:
            title = page.title()
            if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                detected = True
        except Exception:
            pass

        if not detected:
            return False

        log_warning("Cloudflare challenge detected (Turnstile / 'Verify you are human').")
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
        return True

    def _dismiss_popups(self, page: Page):
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
        ]
        for sel in close_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible(timeout=400):
                    elem.click()
                    self._random_sleep(0.3, 0.7)
            except Exception:
                pass

    def _warmup_session(self, page: Page):
        """
        Visits https://www.tiktok.com/ so webmssdk.js initializes valid security tokens
        (msToken & ttwid) before visiting the target profile.
        """
        log_info("Warming up session on https://www.tiktok.com/ (generating valid msToken)...")
        try:
            page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=35000)
            self._random_sleep(3.0, 5.0)
            self._dismiss_popups(page)
            page.mouse.move(random.randint(200, 700), random.randint(200, 600), steps=10)
            self._random_sleep(1.5, 2.5)
        except Exception as exc:
            log_warning(f"Warmup notice (continuing to profile): {exc}")

    def check_session_active(self, page: Page) -> Optional[bool]:
        self._dismiss_popups(page)

        if "/login" in page.url:
            return False

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

        login_btn = page.locator('#header-login-button, button[data-e2e="top-login-button"]').first
        if login_btn.count() > 0:
            try:
                btn_txt = login_btn.inner_text().strip().lower()
                if "log in" in btn_txt:
                    return False
            except Exception:
                pass

        profile_count = page.locator(
            '[data-e2e="profile-icon"], div[data-e2e="inbox-icon"], a[data-e2e="upload-icon"], a[href*="/upload"]'
        ).count()
        if profile_count > 0:
            return True

        return None

    def _find_follow_button(self, page: Page):
        button = page.locator('[data-e2e="follow-button"]').first
        if button.count() == 0 or not button.is_visible():
            button = page.locator(
                'button:has-text("Following"), button:has-text("Follow"), '
                'button:has-text("Friends"), button:has-text("Requested")'
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
        log_step(f"Processing Account: {account_name}")
        result = {
            "account": account_name,
            "status": "Unknown",
            "action": "Failed",
            "detail": ""
        }

        cookie_names = {c.get("name", "") for c in cookies}
        if not any(k in cookie_names for k in ("sessionid", "sessionid_ss", "sid_tt")):
            log_warning(f"Cookie file {account_name} is missing sessionid/sid_tt! Follow requests may fail.")

        with sync_playwright() as p:
            # Native Chromium launch:
            # Relies on native --disable-blink-features=AutomationControlled and --mute-audio flags.
            # No detectable init_script monkey-patches so plugins, webdriver, and AudioContext remain 100% native.
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
            profile = get_random_chrome_profile()
            log_info(f"Launching profile: [bold cyan]{profile['name']}[/bold cyan]")

            # Context configuration:
            # When user_agent is None, Playwright uses Chromium's native Desktop User-Agent,
            # ensuring Sec-CH-UA, navigator.platform, and TLS/JA3 fingerprints match 100%.
            context_kwargs = {
                "viewport": profile["viewport"],
                "is_mobile": False,
                "has_touch": False,
                "device_scale_factor": 1,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "ignore_https_errors": True,
            }
            if profile.get("user_agent"):
                context_kwargs["user_agent"] = profile["user_agent"]
                if profile.get("sec_ch_ua"):
                    context_kwargs["extra_http_headers"] = {
                        "sec-ch-ua": profile["sec_ch_ua"],
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                    }

            context: BrowserContext = browser.new_context(**context_kwargs)
            page: Page = context.new_page()

            try:
                log_info(f"Injecting {len(cookies)} cookies into browser context...")
                try:
                    context.add_cookies(cookies)
                except Exception:
                    for c in cookies:
                        try:
                            context.add_cookies([c])
                        except Exception:
                            pass

                # Step 1: Automatic msToken Session Warmup
                # If cookie file does not have an active msToken, warm up on https://www.tiktok.com/
                has_mstoken = any(c.get("name") == "msToken" and c.get("value") for c in cookies)
                if not has_mstoken:
                    log_info("No active msToken found in cookies. Warming up session on https://www.tiktok.com/...")
                    self._warmup_session(page)
                else:
                    log_info("Active msToken present in cookies; skipping warmup.")

                # Step 2: Navigate to target creator profile
                log_info(f"Navigating to target profile: {target_profile_url}")
                page_resp = page.goto(target_profile_url, wait_until="domcontentloaded", timeout=45000)
                self._random_sleep(2.5, 4.0)

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

                if self._check_and_handle_cloudflare(page):
                    title = page.title()
                    if any(t in title.lower() for t in ("just a moment", "cloudflare", "checking your browser")):
                        result["action"] = "Cloudflare Blocked"
                        result["detail"] = "Cloudflare challenge not resolved"
                        return result

                self._dismiss_popups(page)

                # Step 3: Verify login session
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

                # Check initial server relation before clicking
                initial_relation = page.evaluate("""() => {
                    try {
                        const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        if (!el) return null;
                        const data = JSON.parse(el.textContent);
                        const scope = data?.['__DEFAULT_SCOPE__'] || {};
                        const userDetail = scope?.['webapp.user-detail']?.userInfo;
                        const rel = userDetail?.user?.relation;
                        return typeof rel === 'number' ? rel : null;
                    } catch(e) { return null; }
                }""")

                # Step 4: Find follow button
                follow_btn = self._find_follow_button(page)
                if follow_btn.count() == 0 or not follow_btn.is_visible():
                    try:
                        page.wait_for_selector('[data-e2e="follow-button"]', timeout=5000)
                        follow_btn = self._find_follow_button(page)
                    except Exception:
                        pass

                if follow_btn.count() == 0 or not follow_btn.is_visible(timeout=2000):
                    log_warning("Follow button not found on page.")
                    result["action"] = "Failed"
                    result["detail"] = "Follow button not found"
                    return result

                state = self._follow_state(follow_btn)
                log_info(f"Initial follow state: button='{state}', server relation={initial_relation}")

                if (initial_relation is not None and initial_relation in (1, 2)) or state == "following":
                    log_success(f"ALREADY FOLLOWING: {account_name} is already following target!")
                    result["status"] = "Active"
                    result["action"] = "Already Following"
                    result["detail"] = "Already following target"
                    return result

                if state == "requested" or initial_relation == 3:
                    result["status"] = "Active"
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                    return result

                # Step 5: Listen for TikTok's real /commit/follow/user/ API response
                api_result = {"received": False, "status_code": None, "follow_status": None, "msg": "", "http_status": None}

                def on_response(resp):
                    if "commit/follow/user" in resp.url:
                        api_result["received"] = True
                        api_result["http_status"] = resp.status
                        try:
                            payload = resp.json()
                            api_result["status_code"] = payload.get("status_code")
                            api_result["follow_status"] = payload.get("follow_status")
                            api_result["msg"] = payload.get("status_msg", "")
                        except Exception:
                            pass

                page.on("response", on_response)

                # Humanized profile scroll & mouse movement before clicking Follow
                log_info("Simulating human profile activity before clicking Follow...")
                try:
                    page.mouse.move(random.randint(300, 800), random.randint(250, 550), steps=12)
                    page.mouse.wheel(0, random.randint(250, 450))
                    self._random_sleep(1.2, 2.0)
                    page.mouse.wheel(0, -random.randint(250, 450))
                    self._random_sleep(1.0, 1.8)
                except Exception:
                    pass

                self._dismiss_popups(page)

                log_info("Clicking 'Follow' button and waiting for backend API confirmation...")
                follow_btn.scroll_into_view_if_needed()
                self._random_sleep(0.5, 1.0)
                box_elem = follow_btn.bounding_box()
                if box_elem:
                    page.mouse.move(
                        box_elem["x"] + box_elem["width"] / 2 + random.uniform(-6, 6),
                        box_elem["y"] + box_elem["height"] / 2 + random.uniform(-4, 4),
                        steps=15,
                    )
                self._random_sleep(0.3, 0.7)
                follow_btn.click(delay=random.randint(70, 150))

                # Wait specifically for the backend API response (/commit/follow/user/)
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline and not api_result["received"]:
                    self._random_sleep(0.5, 0.8)
                    if page.locator("div#tiktok-verify-ele, div[class*='captcha']").first.is_visible():
                        log_warning("TikTok CAPTCHA challenge popped up!")
                        result["action"] = "Captcha Triggered"
                        result["detail"] = "Captcha challenge triggered"
                        return result

                if not api_result["received"]:
                    log_warning("Did not observe /commit/follow/user/ network call (blocked by frontend or login wall).")
                else:
                    if api_result["status_code"] != 0 or api_result["follow_status"] in (0, None):
                        msg = api_result["msg"] or f"status_code={api_result['status_code']}"
                        log_error(f"TikTok backend rejected follow: {msg}")
                        result["action"] = "Action Blocked"
                        result["detail"] = f"Backend rejected: {msg}"
                        return result
                    log_info(f"Follow API returned status_code=0, follow_status={api_result['follow_status']}.")

                # Step 6: Wait 5 seconds, then reload profile page for real server verification
                log_info("Waiting 5s for TikTok backend synchronization before verification...")
                time.sleep(5)

                log_info("Reloading profile page to verify server hydration and button persistence...")
                page.reload(wait_until="domcontentloaded", timeout=35000)
                self._random_sleep(2.0, 3.5)
                self._dismiss_popups(page)

                # Check server hydration state (userInfo.user.relation in 1, 2)
                server_relation = page.evaluate("""() => {
                    try {
                        const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        if (!el) return null;
                        const data = JSON.parse(el.textContent);
                        const scope = data?.['__DEFAULT_SCOPE__'] || {};
                        const userDetail = scope?.['webapp.user-detail']?.userInfo;
                        const rel = userDetail?.user?.relation;
                        return typeof rel === 'number' ? rel : null;
                    } catch (e) {
                        return null;
                    }
                }""")

                # Check reloaded button state
                follow_btn_after = self._find_follow_button(page)
                if follow_btn_after.count() > 0:
                    persisted_state = self._follow_state(follow_btn_after)
                else:
                    persisted_state = "unknown"

                log_info(f"Post-reload verification: server relation={server_relation}, button state='{persisted_state}'")

                if (server_relation is not None and server_relation in (1, 2)) or persisted_state in ("following", "friends"):
                    log_success(f"FOLLOWED & VERIFIED: {account_name} follow confirmed on server! (relation={server_relation}, button={persisted_state})")
                    result["action"] = "Followed"
                    result["detail"] = f"Verified (relation={server_relation}, button={persisted_state})"
                elif persisted_state == "requested" or server_relation == 3:
                    log_warning(f"Follow request persisted (private account): {account_name}")
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                else:
                    log_warning(
                        f"GHOST FOLLOW DETECTED: Button reverted to '{persisted_state}' (relation={server_relation}) after reload! "
                        "TikTok silently dropped the follow (IP/proxy trust score or account rate limit)."
                    )
                    result["action"] = "Shadow-Dropped"
                    result["detail"] = f"Ghost follow (relation={server_relation}, button={persisted_state})"

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
