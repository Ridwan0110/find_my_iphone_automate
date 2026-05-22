"""
find_my_iphone_automate: A script to automatically ping you whenever one of your iCloud device is online in Find My.
"""
# Imports
import sys
import time
import json
import redu_logger, redu_config_manager, redu_build_manager
import requests
from pathlib import Path
from datetime import datetime
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudAPIResponseException
from neonize.client import NewClient
from neonize.utils import build_jid
from readchar import readkey

__version__ = "0.0.2"

# Initialize PathLIB Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE_PATH = DATA_DIR / "config.yaml"
BUILD_FILE_PATH = DATA_DIR / "BUILD"
NEONIZE_SESSION_FILE_PATH = DATA_DIR / "session.db"

# Ensure `config.yaml` exists and is a YAML mapping so the config manager loads a dict
if not CONFIG_FILE_PATH.exists() or CONFIG_FILE_PATH.stat().st_size == 0:
    CONFIG_FILE_PATH.write_text("{}\n")

# Ensure BUILD file exists
if not BUILD_FILE_PATH.exists():
    BUILD_FILE_PATH.touch()

# Initialize the logger
logger = redu_logger.RemoteLogger(True, False)

# Initialize config manager
config_manager = redu_config_manager.ConfigManager(CONFIG_FILE_PATH)
# Initialize build manager
enable_build_manager = True  # False on release
build_manager = redu_build_manager.BuildManager(enable_build=enable_build_manager, build_file=BUILD_FILE_PATH, )


def initialize() -> tuple[str, str, str, int]:
    """Initializes the script"""
    initialized = bool(config_manager.get_value("initialized"))
    if not initialized:
        logger.info("Script not initialized. Initializing...")
        apple_id = input("Your Apple ID: ")
        password = input("Your Apple ID Password: ")
        target_device_model = input("Target Device Model: ")

        config_manager.set_value("apple_id", apple_id)
        config_manager.set_value("password", password)
        config_manager.set_value("target_device_model", target_device_model)
        config_manager.set_value("poll_interval_seconds", 180)
        config_manager.save_config()

        return apple_id, password, target_device_model, 180
    else:
        apple_id = config_manager.get_value("apple_id")
        password = config_manager.get_value("password")
        target_device_model = config_manager.get_value("target_device_model")
        try:
            poll_interval_seconds = int(config_manager.get_value("poll_interval_seconds"))
        except ValueError:
            logger.error("Invalid value of 'poll_interval_seconds' in config file. Defaulting to 180", True)
            poll_interval_seconds = 180

        return apple_id, password, target_device_model, poll_interval_seconds

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
        logger.error("Authentication failed. Please verify your system keyring credentials.", True)
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

def initialize_neonize():
    if Path.exists(NEONIZE_SESSION_FILE_PATH):
        client = NewClient(str(NEONIZE_SESSION_FILE_PATH))
        return client
    else:
        logger.info("Neonize Session file doesn't exist. Creating...")
        print("Please scan the QR code to login to you WhatsApp account. Press any key to continue...")
        readkey()
        client = NewClient(str(NEONIZE_SESSION_FILE_PATH))
        return client

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

    message = (f"\n{"=" * 60}"
               f"\nALERT: {device_name}/{device_model} IS ONLINE / POSITION UPDATED"
               f"\nTimestamp: {readable_time}"
               f"\nCoordinates: {latitude}, {longitude}"
               f"\nAccuracy  : Within {round(accuracy, 2)} meters"
               f"\nGoogle Maps Link: {maps_url}"
               f"\n{"=" * 60}\n")
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
        whatsapp_client.connect()
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

                # Ensure recipient is a JID
                recipient_jid = build_jid(recipient)
                
                # Send the message
                whatsapp_client.send_message(recipient_jid, message)
                logger.info(f"WhatsApp message delivered to {recipient}.", True)
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message to {recipient}: {e}", True)
        whatsapp_client.disconnect()

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
    main()
