# TikTok Multi-Account Auto-Follower 🚀

An automated Python tool designed to manage and follow TikTok creators across multiple accounts simultaneously using saved session cookies—avoiding manual credentials login, captchas, and account locks.

> **Developer:** @hydra_X001  
> **Telegram:** [https://t.me/hydrax001](https://t.me/hydrax001)

---

## 🌟 Key Features

- **Multi-Account Cycling:** Processes entire folders of `.txt` or `.json` cookie files with parallel browser concurrency (`1-10+`).
- **TLS/JA3 Fingerprint Spoofing (curl_cffi):** Uses `curl_cffi` impersonating genuine Google Chrome 131 TLS/JA3/HTTP2 stacks for instant 0.3s pre-flight checks, bypassing Cloudflare bot detection.
- **Instant Skip for Already Following:** Checks follow relations directly in 0.3s without opening a browser window; automatically skips cooldowns.
- **Clean Chrome TLS-to-UA Alignment:** Playwright browser strictly matches Chromium BoringSSL TLS handshakes with standard Google Chrome user-agents and Client Hints, preventing Cloudflare JA3-mismatch flags.
- **Silent Audio Muting:** Completely mutes all browser audio via `--mute-audio` so TikTok video sounds never interrupt you while running.
- **Proxy Rotation Support:** Built-in round-robin proxy rotation (`ip:port`, `ip:port:user:pass`, `socks5://...`, or direct network).
- **Deterministic Session Health:** Directly queries TikTok's internal application state (`__UNIVERSAL_DATA_FOR_REHYDRATION__`) to confirm active vs. dead accounts with 100% accuracy.
- **Smart RFC 6265bis Cookie Parser:** Automatically normalizes `__Host-` cookies, `#HttpOnly_` prefixes, and companion security tokens without crashing Chromium.
- **Advanced Anti-CAPTCHA Protections:**
  - Automated humanized profile scrolling and For You feed warm-up.
  - Automatic dismissal of "Create a passkey", "Stay in browser", and app promotion popups.
  - Natural hover pauses (`400–800ms`) and realistic click durations (`60–140ms`).
  - Playwright Stealth evasion patches with randomized viewports and device touch emulation.
- **Dual Display Modes:** Choose interactively between **Visible Browser Window** (to observe automation) or **Headless Mode** (silent background execution).
- **Intelligent URL Cleaning:** Strips mobile tracking/referral parameters (`?_r=1&_t=...`) from share links to avoid mobile app installation popups.
- **State Confirmation Polling:** Automatically verifies if the account transitioned to `Following` or `Requested` before concluding.
- **Rich Terminal Summary:** Displays a clean, colored status table of every account upon completion.

---

## 📁 Project Structure

```text
tiktok-automation/
│
├── utils/
│   ├── __init__.py
│   ├── cookie_parser.py         # Multi-format cookie normalizer
│   ├── proxy_parser.py          # Proxy loader and rotator
│   └── logger.py                # Rich terminal logging & execution tables
│
├── bot.py                       # Playwright & curl_cffi hybrid automation core
├── main.py                      # Interactive CLI entrypoint
├── user_agent.py                # Standard Chrome TLS/JA3-matched profiles
├── user-agent.py                # Direct alias & standalone inspection script
├── run.bat                      # 1-click Windows launcher
├── requirements.txt             # Python dependencies
├── LICENSE                      # MIT License
└── README.md                    # Documentation
```

---

## 🛠️ Step 1: Installation & Setup

### 1. Open Terminal
Open PowerShell or Command Prompt in the project folder:
```powershell
cd c:\Users\Hydra\Desktop\tiktok-automation
```

### 2. Install Dependencies
Install all required libraries:
```powershell
pip install -r requirements.txt
```

### 3. Install Playwright Chromium Browser
If running Playwright for the first time:
```powershell
playwright install chromium
```

---

## 🍪 Step 2: Preparing Your Cookie Files

Place your `.txt` cookie files inside the `cookies/` folder (or select any custom folder on your computer when prompted).

Supported formats include:
- **Netscape format** (standard tab-delimited exported by cookie checkers / HYDRA_X001 software)
- **JSON array format** (exported via browser extensions like *Cookie-Editor*)
- **Key-Value / Header format** (`sessionid=xxxx; sid_guard=yyyy`)

> **Note:** Each account should be saved in its own `.txt` file (e.g. `account1.txt`, `account2.txt`, etc.).

---

## 🚀 Step 3: Running the Automation

### Method A: One-Click Launcher (Easiest)

Simply double-click **`run.bat`** (or execute `.\run.bat` in your terminal).

It will automatically:
1. Verify Python is installed
2. Check and auto-install any missing dependencies (`pip install -r requirements.txt`)
3. Check and auto-install Playwright Chromium if needed
4. Launch `main.py` directly

```powershell
.\run.bat
```

Or run via Python directly:
```powershell
python main.py
```

The script will guide you through simple prompts:

1. **Enter cookie folder:**  
   Path to your cookies (e.g. `cookies` or `C:\Users\Hydra\Desktop\tiktok`).
   ```text
   Enter the folder containing TikTok .txt cookie files: C:\Users\Hydra\Desktop\tiktok
   ```

2. **Enter target profile:**  
   Accepts `@username`, clean username, or full share URL:
   ```text
   Enter target TikTok @username or profile URL: https://www.tiktok.com/@kamal_sharmz
   ```

3. **Select Browser Display Mode:**  
   Choose between visible window or headless background:
   ```text
   Select Browser Display Mode:
     1. Visible Browser Window (Default / Recommended to reduce CAPTCHAs)
     2. Headless Mode (Silent background execution, no window)
   Enter choice [1/2] (default: 1): 1
   ```

4. **Select Concurrent Browsers:**  
   Run 1 browser at a time or launch multiple in parallel:
   ```text
   Select Concurrent Browsers:
     Enter 1 to run one by one, or 2+ to launch multiple browsers in parallel.
   Enter number of concurrent browsers [1-10] (default: 1): 2
   ```

5. **Proxy Configuration (Optional):**  
   Enter a path to `proxies.txt` or a proxy string, or simply press **Enter** to skip and use your direct network:
   ```text
   Proxy Configuration (Optional):
     Supports proxies.txt or ip:port / user:pass@ip:port. Press Enter to skip.
   Enter proxy file path or proxy (press Enter for Direct Connection): proxies.txt
   ```

6. **Enter Cooldown Delay:**  
   Time in seconds to wait between switching accounts (press Enter to keep default 15.0s):
   ```text
   Enter cooldown delay between accounts in seconds (default: 15.0): 
   ```

---

### Method B: Command-Line Shortcut (Fastest)

You can pass arguments directly to bypass prompts:

#### 1. Visible Browser Window with 2 Concurrent Workers & Proxies:
```powershell
python main.py -t "@kamal_sharmz" -c "C:\Users\Hydra\Desktop\tiktok" --concurrency 2 --proxy proxies.txt --visible
```

#### 2. Headless Mode (Silent Background Execution):
```powershell
python main.py -t "@kamal_sharmz" -c "C:\Users\Hydra\Desktop\tiktok" --headless --concurrency 3
```

#### 3. Single Direct Connection with Custom Delay:
```powershell
python main.py -t "@kamal_sharmz" -c "C:\Users\Hydra\Desktop\tiktok" --delay 20
```

---

## 🌐 Proxy Support & Formats

If you supply a proxy file or string, the bot will automatically round-robin rotate through them across all accounts and workers.

Supported formats:
- `ip:port`
- `ip:port:user:password`
- `user:password@ip:port`
- `http://user:password@ip:port`
- `socks5://ip:port`
- `socks5://user:password@ip:port`

> **Tip:** You can create a file named `proxies.txt` in the project root with one proxy per line. If no proxies are provided, the bot uses your direct internet connection.

---

## ⚙️ Available Command-Line Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `--target` | `-t` | Target TikTok `@username` or profile URL | *Prompts interactively* |
| `--cookies` | `-c` | Path to folder containing `.txt` cookie files (or single file) | *Prompts interactively* |
| `--concurrency` | `-w` | Number of concurrent browsers to run simultaneously (`1-10`) | `1` |
| `--proxy` | `-p` | Path to `proxies.txt` or single proxy string (optional) | *Direct Connection* |
| `--visible` | | Runs browser in visible window mode | *Default interactive choice* |
| `--headless`| | Runs browser silently in background | *Disabled by default* |
| `--delay` | | Cooldown delay in seconds between accounts | `15.0` |
| `--help` | `-h` | Shows help message with all options | |

---

## 🛡️ Anti-Ban & Anti-CAPTCHA Best Practices

1. **Always Use Visible Mode for High-Volume Runs:** Visible window mode utilizes your GPU's full rendering pipeline and avoids headless fingerprint detection.
2. **Realistic Cooldowns:** Keep at least `5–15` seconds cooldown between accounts (`--delay 10`) to prevent TikTok from flagging your IP.
3. **Clean IP / Residential Connection:** Avoid low-quality free datacenter proxies or VPNs that are already blacklisted by TikTok's security firewall.
4. **Session Integrity:** If an account shows `Dead`, log into that account in your regular browser to verify if TikTok requested a password reset or email verification, then re-export the cookie.

---

## 👨‍💻 Developer & Support

- **Created by:** @hydra_X001
- **Official Telegram:** [https://t.me/hydrax001](https://t.me/hydrax001)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - free to use, edit, modify, and distribute by hydra (@hydra_X001).
