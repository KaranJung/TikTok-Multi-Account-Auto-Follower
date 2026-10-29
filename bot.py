"""
TikTok browser automation with native Chromium identity and verified TLS.
Security challenges pause automation for manual attention in visible mode.
Unresolved challenges and rate limits stop queued accounts without deleting cookies.
A successful page load does not establish permission or guarantee follow success.
"""
import json
import re
import time
import random
from threading import Event
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from utils.logger import log_info, log_success, log_warning, log_error, log_step


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
    def __init__(self, headless: bool = False, challenge_timeout: int = 120):
        if challenge_timeout < 0:
            raise ValueError("challenge_timeout must be non-negative")
        self.headless = headless
        self.challenge_timeout = challenge_timeout
        self.stop_event = Event()

    def _random_sleep(self, min_sec: float = 1.5, max_sec: float = 3.5):
        time.sleep(random.uniform(min_sec, max_sec))

    def _detect_challenge(self, page: Page) -> Optional[str]:
        selectors = {
            "Cloudflare Blocked": (
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
                '#challenge-stage', '#challenge-running', '#cf-challenge-running',
                '.cf-challenge-running', 'div[class*="CloudflarePopup"]',
                'h1:has-text("Verify you are human")',
                'h2:has-text("Checking if the site connection is secure")',
            ),
            "Captcha Triggered": (
                '#tiktok-verify-ele', '[id*="captcha"]',
                '[class*="captcha"]', 'iframe[src*="captcha"]',
            ),
        }
        for action, choices in selectors.items():
            for selector in choices:
                try:
                    if page.locator(f"{selector}:visible").count() > 0:
                        return action
                except Exception:
                    pass
        try:
            title = page.title().strip().lower()
            if title.startswith(("just a moment", "checking your browser", "attention required! | cloudflare")):
                return "Cloudflare Blocked"
        except Exception:
            pass
        return None

    def _wait_for_challenge(self, page: Page, response=None) -> Optional[str]:
        """Return a blocking action, or None only when access can continue."""
        if page.is_closed():
            return "Browser Closed"
        if response is not None and response.status == 429:
            log_warning("HTTP 429: rate limited on this account/proxy.")
            return "Rate Limited"
        challenge = self._detect_challenge(page)
        if not challenge and response is not None:
            if response.header_value("cf-mitigated") == "challenge":
                challenge = "Cloudflare Blocked"
        if not challenge:
            if response is not None and response.status == 403:
                return "Access Blocked"
            if response is not None and response.status >= 400:
                return "Network Error"
            return None
        if self.headless or self.challenge_timeout == 0:
            log_warning(f"{challenge}: security challenge detected; skipping account.")
            return challenge

        log_warning(
            f"{challenge}: automation paused for up to {self.challenge_timeout}s. "
            "Complete the security check manually in the browser. Do not change the network."
        )
        deadline = time.monotonic() + self.challenge_timeout
        clear_checks = 0
        while time.monotonic() < deadline:
            if page.is_closed():
                return "Browser Closed"
            if self.stop_event.is_set():
                return challenge
            current = self._detect_challenge(page)
            ready = False
            if not current:
                try:
                    ready = page.locator(
                        'script#__UNIVERSAL_DATA_FOR_REHYDRATION__, script#SIGI_STATE, '
                        '[data-e2e="user-title"]:visible, #header-login-button:visible'
                    ).count() > 0
                except Exception:
                    pass
            clear_checks = clear_checks + 1 if ready else 0
            if clear_checks >= 3:
                log_info("Challenge no longer visible; rechecking the session before any action.")
                return None
            page.wait_for_timeout(500)
        log_warning("Challenge remains unresolved; skipping account.")
        return challenge

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
        Visits https://www.tiktok.com/ so webmssdk.js mints a fresh, IP-matched
        msToken and ttwid before visiting the target profile.
        """
        log_info("Opening TikTok home page to check session access...")
        try:
            response = page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(1000)
            blocked = self._wait_for_challenge(page, response)
            if blocked:
                return blocked
            self._dismiss_popups(page)
            return None
        except Exception as exc:
            log_warning(f"Session page could not be loaded: {type(exc).__name__}; cookies preserved.")
            raise

    def check_session_active(self, page: Page) -> Optional[bool]:
        if self._detect_challenge(page):
            return None

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

        login_btn = page.locator('#header-login-button:visible, button[data-e2e="top-login-button"]:visible').first
        if login_btn.count() > 0:
            try:
                btn_txt = login_btn.inner_text().strip().lower()
                if "log in" in btn_txt:
                    return False
            except Exception:
                pass

        profile_count = page.locator(
            '[data-e2e="profile-icon"]:visible, div[data-e2e="inbox-icon"]:visible, a[data-e2e="upload-icon"]:visible, a[href*="/upload"]:visible'
        ).count()
        if profile_count > 0:
            return True

        return None

    def _find_follow_button(self, page: Page):
        # Target profile header containers have priority over sidebar suggested accounts
        header_selectors = [
            '[data-e2e="user-page-header"] [data-e2e="follow-button"]:visible',
            '[data-e2e="user-header"] [data-e2e="follow-button"]:visible',
            'div[class*="ShareTitle"] [data-e2e="follow-button"]:visible',
            'div[class*="DivUserContainer"] [data-e2e="follow-button"]:visible',
            'div[class*="DivShareTitle"] [data-e2e="follow-button"]:visible',
        ]
        for sel in header_selectors:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first

        # Fallback to the first visible follow button in the DOM (the profile header is at the top)
        buttons = page.locator('[data-e2e="follow-button"]:visible')
        if buttons.count() > 0:
            return buttons.first

        # Fallback for dynamic class buttons inside the user header
        header_btn = page.locator('[data-e2e="user-page-header"] button:visible, [data-e2e="user-header"] button:visible')
        for i in range(header_btn.count()):
            btn = header_btn.nth(i)
            txt = (btn.inner_text() or "").strip().lower()
            if any(k in txt for k in ("follow", "following", "requested", "friends")):
                return btn

        return buttons.first

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
        if self.stop_event.is_set():
            result.update(action="Skipped", detail="Batch stopped after a security block")
            return result

        # Strip any stale msToken from exported cookies so fresh token is generated for current IP
        cookies = [c for c in cookies if c.get("name") != "msToken"]

        cookie_names = {c.get("name", "") for c in cookies}
        if not any(k in cookie_names for k in ("sessionid", "sessionid_ss", "sid_tt")):
            log_warning(f"Cookie file {account_name} is missing sessionid/sid_tt! Follow requests may fail.")

        with sync_playwright() as p:
            # Native Chromium launch:
            # Relies on native --disable-blink-features=AutomationControlled and --mute-audio flags.
            # Passes --headless=new when in headless mode to use modern headless Chrome.
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--mute-audio",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors",
                "--allow-running-insecure-content",
            ]
            if self.headless:
                launch_args.append("--headless=new")

            launch_kwargs = {
                "headless": self.headless,
                "ignore_default_args": ["--enable-automation"],
                "args": launch_args,
            }
            if proxy:
                launch_kwargs["proxy"] = proxy
                log_info(f"Using proxy: [bold yellow]{proxy.get('server')}[/bold yellow]")

            browser: Browser = p.chromium.launch(**launch_kwargs)
            log_info(f"Native Chromium {browser.version}; native UA/client hints; anti-detection flags active.")

            context_kwargs = {
                "viewport": {"width": 1440, "height": 900},
                "ignore_https_errors": True,
            }

            context: BrowserContext = browser.new_context(**context_kwargs)
            page: Page = context.new_page()

            try:
                log_info(f"Injecting {len(cookies)} cookies into browser context...")
                try:
                    context.add_cookies(cookies)
                except Exception:
                    log_error("Cookie injection failed; preserving the file for inspection.")
                    result.update(action="Cookie Error", detail="Browser rejected cookie data; file preserved")
                    return result

                # Step 1: Always warm up session on TikTok home feed so webmssdk.js mints a fresh msToken for this IP
                blocked = self._warmup_session(page)
                if blocked:
                    result.update(action=blocked, detail="Home page access failed; cookies preserved")
                    return result

                # Step 2: Navigate to target creator profile
                log_info(f"Navigating to target profile: {target_profile_url}")
                page_resp = page.goto(target_profile_url, wait_until="domcontentloaded", timeout=45000)
                self._random_sleep(2.5, 4.0)

                blocked = self._wait_for_challenge(page, page_resp)
                if blocked:
                    result.update(action=blocked, detail="Profile access blocked; cookies preserved")
                    return result

                try:
                    body_text = page.locator("body").inner_text(timeout=1000).strip().lower()
                    if body_text == "forbidden" or "access denied" in body_text:
                        log_error(f"Access denied for {account_name}; skipping account.")
                        result["action"] = "Access Blocked"
                        result["detail"] = "Access denied; cookies preserved"
                        return result
                except Exception:
                    pass

                self._dismiss_popups(page)

                # Step 3: Verify login session
                is_alive = self.check_session_active(page)
                if is_alive is not True:
                    result["status"] = "Login Required" if is_alive is False else "Unknown"
                    result["action"] = "Skipped"
                    result["detail"] = "Authenticated session not confirmed; cookie file preserved"
                    log_warning(result["detail"])
                    return result
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

                if state == "following" and initial_relation in (None, 1, 2):
                    log_success(f"ALREADY FOLLOWING: {account_name} is already following target!")
                    result["status"] = "Active"
                    result["action"] = "Already Following"
                    result["detail"] = "Already following target"
                    return result

                if state == "requested" and initial_relation in (None, 3):
                    result["status"] = "Active"
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                    return result
                if state != "follow" or initial_relation not in (None, 0):
                    result.update(action="Verification Inconclusive", detail="Follow state is ambiguous or conflicts with server data; no click")
                    return result

                # Step 5: Listen for TikTok's real follow API response
                api_result = {
                    "received": False,
                    "status_code": None,
                    "follow_status": None,
                    "msg": "",
                    "http_status": None,
                }

                def on_response(resp):
                    try:
                        # Only examine POST requests to follow-related endpoints (ignore OPTIONS preflight)
                        if resp.request.method != "POST":
                            return
                        url = resp.url
                        if any(k in url for k in ("commit/follow/user", "user/follow", "relation/follow")):
                            api_result["received"] = True
                            api_result["http_status"] = resp.status
                            try:
                                payload = resp.json()
                                if isinstance(payload, dict):
                                    sc = payload.get("status_code", payload.get("statusCode"))
                                    fs = payload.get("follow_status", payload.get("followStatus"))
                                    sm = payload.get("status_msg", payload.get("statusMsg", payload.get("message", "")))
                                    if sc is not None:
                                        api_result["status_code"] = int(sc)
                                    if fs is not None:
                                        api_result["follow_status"] = int(fs)
                                    if sm:
                                        api_result["msg"] = str(sm)
                            except Exception:
                                pass
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

                blocked = self._wait_for_challenge(page)
                if blocked:
                    result.update(action=blocked, detail="Security check before follow; cookies preserved")
                    return result
                if self.stop_event.is_set() or self.check_session_active(page) is not True:
                    result.update(action="Skipped", detail="Batch stopped or authentication no longer confirmed")
                    return result
                if self._follow_state(follow_btn) != "follow":
                    result.update(action="Skipped", detail="Follow button state changed; no click performed")
                    return result

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
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not api_result["received"]:
                    page.wait_for_timeout(500)
                    blocked = self._wait_for_challenge(page)
                    if blocked:
                        result.update(action=blocked, detail="Security check after click; follow not confirmed")
                        return result

                blocked = self._wait_for_challenge(page)
                if blocked:
                    result.update(action=blocked, detail="Security check after follow response; follow not confirmed")
                    return result

                # Anti-Unfollow Retry Guard:
                # Crucial safeguard: ONLY retry click if the button strictly remains in 'follow' state.
                # If it already flipped to 'following', 'friends', or 'requested', NEVER click again!
                if not api_result["received"]:
                    log_warning("No follow response captured. No automatic retry; checking persistence only.")

                http_status = api_result["http_status"]
                if http_status is not None and http_status >= 400:
                    action = "Rate Limited" if http_status == 429 else "Action Blocked"
                    result.update(action=action, detail=f"Follow request HTTP {http_status}; no retry")
                    return result

                # Evaluate backend API response:
                # ONLY reject immediately if the backend returned an explicit non-zero error code (e.g. 2049 = rate limited)
                if api_result["received"]:
                    sc = api_result["status_code"]
                    msg = api_result["msg"]
                    if sc is not None and sc != 0:
                        err_msg = msg or f"code {sc}"
                        log_error(f"TikTok backend rejected follow: {err_msg}")
                        result["action"] = "Action Blocked"
                        result["detail"] = f"Backend rejected: {err_msg}"
                        return result
                    elif sc == 0:
                        log_info("TikTok backend confirmed follow request (status_code=0).")
                    else:
                        log_info("Backend follow call detected. Verifying persistence via profile reload...")
                else:
                    log_info("Follow button clicked. Verifying persistence via profile reload...")

                # Step 6: Wait 5 seconds, then reload profile page for real server verification
                log_info("Waiting 5s for TikTok backend synchronization before verification...")
                page.wait_for_timeout(5000)

                log_info("Reloading profile page to verify server hydration and button persistence...")
                verification_response = page.reload(wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(2000)
                blocked = self._wait_for_challenge(page, verification_response)
                if blocked:
                    result.update(action=blocked, detail="Security check during verification; follow not confirmed")
                    return result
                if self.check_session_active(page) is not True:
                    result.update(action="Verification Inconclusive", detail="Authentication not confirmed after reload")
                    return result
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

                if persisted_state == "following" and server_relation in (None, 1, 2):
                    log_success(f"FOLLOWED & VERIFIED: {account_name} follow confirmed on server! (relation={server_relation}, button={persisted_state})")
                    result["action"] = "Followed"
                    result["detail"] = f"Verified (relation={server_relation}, button={persisted_state})"
                elif persisted_state == "requested" and server_relation in (None, 3):
                    log_warning(f"Follow request persisted (private account): {account_name}")
                    result["action"] = "Requested"
                    result["detail"] = "Follow request pending"
                else:
                    log_warning(
                        f"Follow not verified after reload (relation={server_relation}, button={persisted_state}). "
                        "The response does not establish a cause; no automatic retry."
                    )
                    result["action"] = "Verification Inconclusive"
                    result["detail"] = f"Not verified (relation={server_relation}, button={persisted_state})"

                return result

            except Exception as e:
                err_msg = str(e)
                if page.is_closed():
                    result.update(action="Browser Closed", detail="Browser closed before verification; cookies preserved")
                    return result
                if any(k in err_msg for k in ("ERR_PROXY", "ERR_TUNNEL", "ERR_CERT", "ERR_SSL", "ERR_HTTP_RESPONSE_CODE_FAILURE", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_CLOSED")):
                    log_error(f"Proxy network error for {account_name}: {err_msg[:80]}")
                    result["action"] = "Proxy Failed"
                    result["detail"] = f"Proxy error: {err_msg[:40]}"
                    return result
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
