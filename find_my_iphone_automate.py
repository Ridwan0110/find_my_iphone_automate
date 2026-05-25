"""
find_my_iphone_automate: A script to automatically ping you whenever one of your iCloud device is online in Find My.
"""
# Imports
import os
import sys
import time
import json
import redu_logger, redu_config_manager, redu_build_manager
import requests
import threading
from pathlib import Path
from datetime import datetime
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudAPIResponseException
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv
from neonize.utils import build_jid
from dotenv import load_dotenv

# Constants
__version__ = "0.0.3"
tty = sys.stdin.isatty()

# Initialize PathLIB Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE_PATH = DATA_DIR / "config.yaml"
BUILD_FILE_PATH = DATA_DIR / "BUILD"
NEONIZE_SESSION_FILE_PATH = DATA_DIR / "session.db"
DOTENV_FILE_PATH = BASE_DIR / ".env"

# Ensure `config.yaml` exists and is a YAML mapping so the config manager loads a dict
if not CONFIG_FILE_PATH.exists() or CONFIG_FILE_PATH.stat().st_size == 0:
    CONFIG_FILE_PATH.write_text("{}\n")

# Ensure BUILD file exists
if not BUILD_FILE_PATH.exists():
    BUILD_FILE_PATH.touch()

# Loads .env if exists
if DOTENV_FILE_PATH.exists():
    load_dotenv(DOTENV_FILE_PATH)

# Initialize the logger
logger = redu_logger.RemoteLogger(True, False)

# Initialize config manager
config_manager = redu_config_manager.ConfigManager(CONFIG_FILE_PATH)
# Initialize build manager
enable_build_manager = True  # False on release
build_manager = redu_build_manager.BuildManager(enable_build=enable_build_manager, build_file=BUILD_FILE_PATH, )


class WhatsAppClient:
    def __init__(self, session_path: Path):
        logger.info("Initializing WhatsAppClient...")
        self.session_path = session_path

        self.class_name = "WhatsAppClient"
        self.client = NewClient(str(session_path))
        self._lock = threading.Lock()
        self._is_connecting = False
        self._connected = False
        self._qr_showed = False
        self.whatsapp_thread = None

        @self.client.qr
        def on_qr(client, qr_bytes: bytes):
            logger.info(f"[{self.class_name}] QR Code intercepted")
            self._qr_showed = True
            self.client.event._Event__onqr(client, qr_bytes)

        self.client.event(ConnectedEv)(self._on_connected)
        self.client.event(DisconnectedEv)(self._on_disconnect)
        logger.info("Initialized WhatsAppClient")

    def _update_connection_flags(self, connected: bool, is_connecting: bool):
        self._connected = connected
        self._is_connecting = is_connecting

    def _do_connect(self):
        try:
            logger.info(f"[{self.class_name}] Connecting...", True)
            self.client.connect()
        except Exception as e:
            logger.error(f"[{self.class_name}] Failed to connect: {e}", True)
        finally:
            with self._lock:
                self._update_connection_flags(False, False)

    def _on_connected(self, cl, event):
        logger.info(f"[{self.class_name}] Connected", True)
        with self._lock:
            self._update_connection_flags(True, False)

    def _on_disconnect(self, cl, event):
        logger.info(f"[{self.class_name}] Disconnected")
        with self._lock:
            self._update_connection_flags(False, False)

    def _auto_connect(self, timeout: int, retry_count: int) -> bool:
        logger.info(f"[{self.class_name}] Auto-connecting...", True)
        self.connect()

        # Enforce minimum try count
        max_tries = max(1, retry_count)

        for try_count in range(1, max_tries + 1):
            with self._lock:
                if not self._connected and not self._is_connecting:
                    self.connect()

            # Poll for connection status until timeout expires
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._connected:
                    return True  # Exit immediately on successful connection
                time.sleep(0.5)

            # Attempt timed out
            if try_count < max_tries:
                logger.warning(
                    f"[{self.class_name}] Auto-connect attempt {try_count}/{max_tries} failed. Retrying...",
                    True
                )

        # Final check after all attempts are exhausted
        if not self._connected:
            logger.warning(f"[{self.class_name}] Auto-connect failed after {max_tries} attempts", True)
            return False
        return True

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def qr_showed(self) -> bool:
        with self._lock:
            return self._qr_showed

    def connect(self):
        with self._lock:
            if self._connected or self._is_connecting:
                logger.info(f"[{self.class_name}] Already connected or connecting", True)
                return
            self._is_connecting = True

        self.whatsapp_thread = threading.Thread(target=self._do_connect, daemon=True)
        self.whatsapp_thread.start()

    def disconnect(self, timeout: int = 30):
        with self._lock:
            if not self._connected and not self._is_connecting:
                logger.info(f"[{self.class_name}] Already disconnected", True)
                return
            logger.info(f"[{self.class_name}] Disconnecting...")
            self.client.disconnect()
            self._update_connection_flags(False, False)

        if self.whatsapp_thread and self.whatsapp_thread.is_alive():
            self.whatsapp_thread.join(timeout=timeout)

    def send_message(self, recipient: str, message: str, timeout: int = 30, retry_count: int = 1) -> bool:
        """
        Send a WhatsApp message.

        Args:
            recipient: Phone number (with country code, no Plus(+)
            message: Text content
            timeout: For auto-connecting
            retry_count: For auto-connecting. Set 0 or less for no retry.

        Returns:
            bool: True if send was attempted, False if client unavailable
        """
        # Trt to auto-connect if needed
        if not self._connected:
            auto_connect_success = self._auto_connect(timeout, retry_count)
            if not auto_connect_success:
                return False

        with self._lock:
            client_ref = self.client

        try:
            jid = build_jid(recipient)
            client_ref.send_message(jid, message)
            logger.info(f"[{self.class_name}] Message sent to {recipient}", True)
            return True
        except Exception as e:
            logger.error(f"[{self.class_name}] Couldn't sent message to {recipient}: {e}", True)
            return False


def take_input(prompt: str = "", env_key: str = "", required: bool = False) -> str:
    """
    Retrieves a value, prioritizing environment variables, then falling back to
    interactive input if in a TTY, otherwise raising an error if required.
    """
    env_value = os.getenv(env_key)

    if env_value:
        logger.debug(f"Using environment variable '{env_key}'")
        return env_value
    else:
        if required:
            if tty:
                logger.info(f"Environment variable '{env_key}' not found. Prompting user.")
                return input(prompt)
            else:
                logger.error(f"Required environment variable '{env_key}' is missing and not running in interactive mode.")
                raise RuntimeError(f"Required environment variable '{env_key}' is missing")
        else:
            logger.warning(f"Optional environment variable '{env_key}' not found and not running in interactive mode. Returning empty string.", True)
            return ""

def update_config_with_env():
    config_env_map = {
        "apple_id": "APPLE_ID",
        "password": "APPLE_ID_PASSWORD",
        "target_device_model": "TARGET_DEVICE_MODEL",
        "current_alert_method": "ALERT_METHOD",
        "whatsapp_recipients": "WHATSAPP_RECIPIENTS",
        "discord_webhook": "DISCORD_WEBHOOK",
        "poll_interval_seconds": "POLL_INTERVAL_SECONDS"
    }
    config_updated = False

    for config_key, env_key in config_env_map.items():
        env_value = os.getenv(env_key)
        if env_value:
            current_config_value = config_manager.get_value(config_key)
            if str(current_config_value) != str(env_value):
                config_manager.set_value(config_key, env_value)
                config_updated = True
                logger.info(f"Updated config key '{config_key}' from environment variable '{env_key}'")
        else:
            logger.debug(f"Environment variable '{env_key}' not found, skipping config update for '{config_key}'")

    if config_updated:
        config_manager.save_config()
        logger.info("Configuration updated from environment variables and saved.")
    else:
        logger.info("No configuration changes from environment variables needed.")

def initialize() -> tuple[str, str, str, int]:
    """Initializes the script"""
    apple_id = config_manager.get_value("apple_id")
    password = config_manager.get_value("password")
    target_device_model = config_manager.get_value("target_device_model")
    poll_interval_seconds_str = config_manager.get_value("poll_interval_seconds")
    poll_interval_seconds_default = 180

    if not all([apple_id, password, target_device_model]):
        logger.info("Required configuration missing. Gathering initial setup details...")

        apple_id = take_input("Your Apple ID: ", "APPLE_ID", True)
        password = take_input("Your Apple ID Password: ", "APPLE_ID_PASSWORD", True)
        target_device_model = take_input("Target Device Model: ", "TARGET_DEVICE_MODEL", True)

        config_manager.set_value("apple_id", apple_id)
        config_manager.set_value("password", password)
        config_manager.set_value("target_device_model", target_device_model)

        if not poll_interval_seconds_str:
            config_manager.set_value("poll_interval_seconds", poll_interval_seconds_default)  # Default value
            poll_interval_seconds_str = str(poll_interval_seconds_default)

        config_manager.save_config()
        logger.info("Initial setup complete and configuration saved.")
    else:
        logger.info("Configuration loaded from file.")

    try:
        poll_interval_seconds = int(poll_interval_seconds_str) if poll_interval_seconds_str else poll_interval_seconds_default
    except ValueError:
        logger.error(f"Invalid value of 'poll_interval_seconds' in config file. Defaulting to {poll_interval_seconds_default}", True)
        poll_interval_seconds = poll_interval_seconds_default

    return  apple_id, password, target_device_model, poll_interval_seconds

def initialize_icloud(apple_id, password) -> PyiCloudService:
    """Initializes and returns the authenticated iCloud service instance."""
    logger.info(f"Connecting to iCloud Find My service...", True)
    try:
        api = PyiCloudService(apple_id, password)

        # Check if the session is authenticated (skips 2FA for Find My endpoint)
        if api.requires_2fa:
            logger.info("Account requires 2FA for full data, but proceeding with Find My bypass access.", True)
        return api
    except PyiCloudFailedLoginException:
        logger.error("Authentication failed. Please verify your account credentials.", True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Connection initialization failed: {e}", True)
        sys.exit(1)

def initialize_alert_method() -> dict:
    alert_methods = {"Discord Webhook": False, "WhatsApp": False}
    current_method = config_manager.get_value("current_alert_method")

    if not current_method:
        logger.info("No alert method configured yet. Ask the user if they'd like to add one now")
        try:
            choice = input("No alert method configured. Would you like to add one now? (y/N): ").strip().lower()
        except Exception as e:
            logger.error(f"Unexpected Error: {e}. No alert methods configured")
            return alert_methods

        if choice in ("y", "yes"):
            print("Choose alert method:\n1) Discord Webhook\n2) WhatsApp\n3) Both")
            sel = input("Enter choice [1-3]: ").strip()
            if sel == "1":
                config_manager.set_value("current_alert_method", "Discord Webhook", True)
                alert_methods["Discord Webhook"] = True
            elif sel == "2":
                config_manager.set_value("current_alert_method", "WhatsApp", True)
                alert_methods["WhatsApp"] = True
            elif sel == "3":
                config_manager.set_value("current_alert_method", "both", True)
                for k in alert_methods:
                    alert_methods[k] = True
            else:
                logger.error("Invalid selection. No alert method configured.", True)
            logger.info(f"Selected alert method: {sel}")
                    logger.warning("Invalid selection. No alert method configured.", True)
                logger.debug(f"Selected alert method: {choice}")

        return alert_methods

    # Normalize for comparison
    cm = str(current_method).strip().lower()

    if cm == "both":
        for k in alert_methods:
            alert_methods[k] = True
        return alert_methods

    # Otherwise, check if the configured method matches any known method (case-insensitive)
    for key in list(alert_methods.keys()):
        if key.lower() == cm:
            alert_methods[key] = True
            break

    return alert_methods

def initialize_neonize() -> WhatsAppClient:
    whatsapp_client = WhatsAppClient(NEONIZE_SESSION_FILE_PATH)

    if not NEONIZE_SESSION_FILE_PATH.exists():
        logger.info("Neonize session file not found. Setting up new connection...", True)
        print("Please scan the QR code to login to you WhatsApp account. Press enter to continue...")
        sys.stdin.readline()

        while not whatsapp_client.connected:
            whatsapp_client.connect()
            time.sleep(5)

        whatsapp_client.disconnect()
        return whatsapp_client

    return whatsapp_client

def initialize_discord_webhook():
    webhook_url = config_manager.get_value("discord_webhook")
    if webhook_url:
        return webhook_url
    else:
        logger.info("Discord Webhook URL doesn't exist. Prompting user...")
        webhook_url = input("Please enter your discord webhook: ")
        config_manager.set_value("discord_webhook", webhook_url, True)

        return webhook_url

def initialize_whatsapp_recipients() -> list:
    """Retrieves WhatsApp recipient numbers from config or prompts user to add them."""
    stored_recipients = config_manager.get_value("whatsapp_recipients")

    # Try to parse existing recipients from config
    if stored_recipients:
        try:
            recipients = json.loads(stored_recipients) if isinstance(stored_recipients, str) else stored_recipients
            if isinstance(recipients, list) and len(recipients) > 0:
                logger.info(f"Found {len(recipients)} WhatsApp recipient(s) in config.")
                return recipients
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid WhatsApp recipients format in config. Prompting user to re-add them...", True)

    # No valid recipients found, prompt user to add them
    logger.info("No WhatsApp recipients configured. Add recipient phone numbers now.")
    recipients = []

    try:
        while True:
            phone = input("Enter WhatsApp recipient number (country code without +, e.g., 12125551234) or 'done' to finish: ").strip()
            if phone.lower() == "done":
                if len(recipients) == 0:
                    logger.warning("No recipients added. WhatsApp alert method will not work", True)
                    return []
                break

            # Validate: should be all digits, at least 7 digits (minimum is ~7 for some countries)
            if phone.isdigit() and len(phone) >= 7:
                recipients.append(phone)
                logger.info(f"Added recipient: {phone}")
            else:
                logger.error("Invalid format. Enter digits only, with country code (e.g., 12125551234).")

        # Store recipients in config
        if recipients:
            config_manager.set_value("whatsapp_recipients", json.dumps(recipients), True)
            logger.info(f"Saved {len(recipients)} WhatsApp recipient(s) to config.")

    except Exception as e:
        logger.error(f"Error adding WhatsApp recipients: {e}")

    return recipients

def trigger_alert(device_name, device_model, location_data, discord_webhook, whatsapp_client, whatsapp_recipients):
    """Executes notification protocols when a new location coordinate is captured."""
    latitude = location_data.get("latitude")
    longitude = location_data.get("longitude")
    accuracy = location_data.get("horizontalAccuracy")  # Radius of accuracy in meters
    timestamp_ms = location_data.get("timeStamp")

    readable_time = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %I:%M:%S %p')
    maps_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

    message = (f"\n{'=' * 60}"
               f"\nALERT: {device_name}/{device_model} IS ONLINE / POSITION UPDATED"
               f"\nTimestamp: {readable_time}"
               f"\nCoordinates: {latitude}, {longitude}"
               f"\nAccuracy  : Within {round(accuracy, 2)} meters"
               f"\nGoogle Maps Link: {maps_url}"
               f"\n{'=' * 60}\n")
    logger.info(message, True)

    # Check alert methods
    if discord_webhook:
        # Validate webhook URL
        if not isinstance(discord_webhook, str) or not discord_webhook.startswith(("http://", "https://")):
            logger.error("Invalid Discord webhook URL configured.", True)
        else:
            # Truncate message to avoid Discord limits
            max_len = 1900
            content = message if len(message) <= max_len else message[:max_len] + "\n[message truncated]"
            json_data = {"content": content}
            headers = {"User-Agent": f"find_my_iphone_automate/{__version__}"}
            retries = 3
            for attempt in range(1, retries + 1):
                try:
                    response = requests.post(discord_webhook, json=json_data, headers=headers, timeout=10)
                    # Success (Discord webhooks often return 204 No Content)
                    if 200 <= response.status_code < 300 or response.status_code == 204:
                        logger.info("Discord webhook delivered.", True)
                        break
                    # Rate limited
                    if response.status_code == 429:
                        try:
                            retry_after = float(
                                response.headers.get("Retry-After") or response.json().get("retry_after"))
                        except Exception:
                            retry_after = None
                        wait = retry_after if retry_after and retry_after > 0 else 2 * attempt
                        logger.warning(f"Discord rate limited. Waiting {wait}s before retry...", True)
                        time.sleep(wait)
                        continue
                    # Other HTTP errors: log and stop retrying
                    logger.error(f"Discord webhook failed ({response.status_code}): {response.text}", True)
                    break
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Discord webhook request error (attempt {attempt}/{retries}): {e}", True)
                    if attempt == retries:
                        logger.error("Discord webhook failed after retries.", True)
                    else:
                        time.sleep(2 * attempt)

    if whatsapp_client and whatsapp_recipients:
        for recipient in whatsapp_recipients:
            logger.info(f"Sending WhatsApp message to {recipient}...", True)
            try:
                # Wait for connection if not yet connected (up to 10 seconds)
                for _ in range(10):
                    if whatsapp_client.connected:
                        break
                    time.sleep(1)

                if not whatsapp_client.connected:
                    logger.warning(f"WhatsApp client not connected yet. Attempting to send anyway...", True)
                
                # Send the message
                whatsapp_client.send_message(recipient, message)
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message to {recipient}: {e}", True)

def main():
    # Initialize the whole script
    apple_id, password, target_device_model, poll_interval_seconds = initialize()
    alert_methods = initialize_alert_method()
    discord_webhook = None
    whatsapp_client = None
    whatsapp_recipients = []

    if alert_methods["Discord Webhook"]:
        discord_webhook = initialize_discord_webhook()
    if alert_methods["WhatsApp"]:
        whatsapp_client = initialize_neonize()
        whatsapp_recipients = initialize_whatsapp_recipients()

    icloud_api = initialize_icloud(apple_id, password)
    last_known_timestamp = None

    logger.info(f"Listener active. Polling Apple servers every {poll_interval_seconds}s...", True)

    while True:
        try:
            # Request Apple's servers to send an active location refresh command
            icloud_api.devices.refresh()
            logger.debug(f"Found devices: {icloud_api.devices}")

            # Iterate through devices associated with the Apple ID
            for device in icloud_api.devices:
                status = device.status()
                device_name = status.get("name", "Unknown Device")
                device_model = status.get("deviceDisplayName", "Unknown Device Model")


                # Check if this matches your test device or stolen iPhone 14 profile
                if target_device_model.lower() in device_model.lower():
                    location = device.location
                    logger.debug(location)

                    if location:
                        current_timestamp = location.get("timeStamp")

                        # Only trigger alerts if it's a completely new location update
                        if current_timestamp != last_known_timestamp:
                            last_known_timestamp = current_timestamp
                            trigger_alert(device_name, device_model, location, discord_webhook, whatsapp_client, whatsapp_recipients)
                        else:
                            logger.info(f"Checked: {device_model} location is unchanged.", True)
                    else:
                        logger.info(f"Checked: {device_model} is currently offline.", True)
        except PyiCloudAPIResponseException as api_err:
            # Catch transient Apple 503 or 450 server timeout exceptions gracefully
            logger.warning(f"Apple API bottleneck or timeout encountered: {api_err}. Re-establishing link in 30s...")
            time.sleep(30)
            icloud_api = initialize_icloud(apple_id, password)
        except KeyboardInterrupt:
            logger.info("\nAutomated script tracking safely terminated.")
            sys.exit(0)

        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    build_manager.generate_build_version()
    update_config_with_env()
    main()
