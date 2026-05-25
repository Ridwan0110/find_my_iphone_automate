**Analysis:** 2

**Updated:** 25 May 2026, 21:35, UTC+6

# Security & Privacy Analysis: Find My iPhone Automate

This document outlines the security vulnerabilities and potential data leaks identified during the code review of the `find-my-iphone-automate` project.

## 🚨 Critical Vulnerabilities

### 1. Plaintext Credential Storage
*   **Location:** `data/config.yaml` and `main.py` (commented-out legacy code).
*   **Risk:** High. The Apple ID and Password are stored in unencrypted plaintext. Anyone with access to the file system can steal these credentials.
*   **Recommendation:** 
    *   Use the `keyring` library to store credentials in the system's secure vault.
    *   Use environment variables via `python-dotenv` for non-sensitive config.
    *   **Immediately** purge legacy credentials from `main.py`.

### 2. Environment Variable Prioritization for Configuration
*   **Location:** `find_my_iphone_automate.py` (`update_config_with_env`, `initialize`, `take_input`)
*   **Observation:** The script now prioritizes environment variables for configuration values, falling back to interactive prompts in TTY sessions when variables are not set. This significantly improves headless operation and security by reducing the need for plaintext prompts.
*   **Benefit:** Enhances flexibility for deployment in automated environments (e.g., Docker, CI/CD) and offers a more secure way to inject sensitive credentials (like Apple ID/password, webhook URLs) without direct file system exposure.
*   **Recommendation:** Document the expected environment variables (e.g., `APPLE_ID`, `APPLE_ID_PASSWORD`, `ALERT_METHOD`) clearly in the project's `README.md` or a dedicated `config_variables.md` file. Ensure that `config.yaml` is still treated as the primary persistent storage, and environment variables serve as an override or initial fill mechanism.

### 3. WhatsApp Session Hijacking
*   **Location:** `data/session.db`
*   **Risk:** High. This SQLite database contains the authentication tokens for the WhatsApp session. If this file is stolen, an attacker can impersonate the user's WhatsApp account without 2FA.
*   **Recommendation:** Ensure the `data/` directory has restricted file permissions (`chmod 700`) and is never uploaded to cloud storage or git.

---

## ⚠️ Privacy & Data Leaks

### 4. Remote Logging of PII
*   **Location:** `main.py` -> `redu_logger.RemoteLogger(True, False)`
*   **Risk:** Medium. If `RemoteLogger` sends data to an external server, your device names, timestamps, and GPS coordinates are being transmitted to a third party.
*   **Recommendation:** Disable remote logging for sensitive location data or ensure the remote endpoint uses E2EE (End-to-End Encryption).

### 5. Notification Metadata Leakage
*   **Location:** `trigger_alert()` function (Discord Webhooks).
*   **Risk:** Medium. Discord webhooks transmit your location data over the internet to Discord's servers. If the webhook URL is discovered, your real-time location history is public.
*   **Recommendation:** Use a more private notification method (e.g., a self-hosted Gotify instance) or obfuscate coordinates before sending.

### 6. Substring Device Matching
*   **Location:** `main.py` -> `if target_device_model.lower() in device_model.lower():`
*   **Risk:** Low/Medium (Functional). This can lead to "False Positive" alerts if you own multiple devices with similar names (e.g., "iPhone 14" and "iPhone 14 Pro").
*   **Recommendation:** Match by a unique identifier (UDID) or use strict string equality.

---

*Note: For a live list of security tasks and project improvements, see [TODO.md](./TODO.md).*
