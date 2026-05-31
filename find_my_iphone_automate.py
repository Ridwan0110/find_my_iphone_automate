"""
find_my_iphone_automate: A script to automatically ping you whenever one of your iCloud device is online in Find My.
"""
# Imports
import os
import sys
import time
import json
import redu_logger, redu_build_manager
import requests
import hashlib
import base64
from redu_config_manager import ConfigManager
from pathlib import Path
from datetime import datetime, timedelta
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudAPIResponseException
from dotenv import load_dotenv
from getpass import getpass
from cryptography.fernet import Fernet
from typing import Optional
from modules import WhatsAppClient, SensitiveConfigManager

# Constants
__version__ = "0.3.0"
tty = sys.stdin.isatty()
service_name = "find_my_iphone_automate"
sensitive_config_env_map = {
    "apple_id": "APPLE_ID",
    "password": "APPLE_ID_PASSWORD",
    "whatsapp_recipients": "WHATSAPP_RECIPIENTS",
    "discord_webhook": "DISCORD_WEBHOOK",
}
config_env_map = {
    "target_device_model": "TARGET_DEVICE_MODEL",
    "current_alert_method": "ALERT_METHOD",
    "poll_interval_seconds": "POLL_INTERVAL_SECONDS"
}

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
config_manager = ConfigManager(CONFIG_FILE_PATH)
# Initialize build manager
enable_build_manager = True  # False on release
build_manager = redu_build_manager.BuildManager(enable_build=enable_build_manager, build_file=BUILD_FILE_PATH)


def take_input(prompt: str = "", env_key: str = "", required: bool = False, password: bool = False) -> str:
    """
    Retrieves a value, prioritizing environment variables, then falling back to
    interactive input if in a TTY, otherwise raising an error if required.

    Args:
        prompt: The text to display when asking for user input (only used if TTY and env var not set)
        env_key: The name of the environment variable to check for the value
        required: Whether this value is required (if True and not found in env, will prompt user if TTY, otherwise raise an error)
        password: Should treat as password (if True, use 'getpass' to hide the password).

    Raises:
        RuntimeError: If the value is required but not found in environment variables and not running in interactive mode.

    Returns:
        The retrieved value or an empty string if not found and not required.
    """
    env_value = os.getenv(env_key)

    if env_value:
        logger.debug(f"Using environment variable '{env_key}'")
        return env_value
    else:
        if required:
            if tty:
                logger.info(f"Environment variable '{env_key}' not found. Prompting user.")
                if password:
                    return getpass(prompt)
                else:
                    return input(prompt)
            else:
                logger.error(
                    f"Required environment variable '{env_key}' is missing and not running in interactive mode.")
                raise RuntimeError(f"Required environment variable '{env_key}' is missing")
        else:
            if tty:
                logger.info(f"Environment variable '{env_key}' not found. Prompting user.")
                if password:
                    return getpass(prompt)
                else:
                    return input(prompt)
            else:
                logger.warning(
                    f"Optional environment variable '{env_key}' not found and not running in interactive mode. Returning empty string.",
                    True)
                return ""


def update_config_with_env(sensitive_config_manager: SensitiveConfigManager):
    """
    Updates the configuration values from environment variables if they are set, and saves the config if any changes were made.

    Uses encryption.
    """
    config_updated = False

    # For config_env_map
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

    # For sensitive_config_env_map
    for config_key, env_key in sensitive_config_env_map.items():
        env_value = os.getenv(env_key)
        if env_value:
            current_config_value = sensitive_config_manager.get_value(config_key)
            if str(current_config_value) != str(env_value):
                sensitive_config_manager.set_value(config_key, env_value)
                config_updated = True
                logger.info(f"Updated config key '{config_key}' from environment variable '{env_key}'")
        else:
            logger.debug(f"Environment variable '{env_key}' not found, skipping config update for '{config_key}'")

    if config_updated:
        config_manager.save_config()
        logger.info("Configuration updated from environment variables and saved.")
    else:
        logger.info("No configuration changes from environment variables needed.")


def initialize(sensitive_config_manager: SensitiveConfigManager) -> tuple[str, str, str, int]:
    """
    Initializes the script.

    Non-tty friendly. Uses encryption.

    Args:
        sensitive_config_manager: An instance of ``SensitiveConfigManager``

    Returns:
        A tuple containing (apple_id, password, target_device_model, poll_interval_seconds)
    """
    apple_id = sensitive_config_manager.get_value("apple_id")
    password = sensitive_config_manager.get_value("password")
    target_device_model = config_manager.get_value("target_device_model")
    poll_interval_seconds_str = config_manager.get_value("poll_interval_seconds")
    poll_interval_seconds_default = 180

    if not all([apple_id, password, target_device_model]):
        logger.info("Required configuration missing. Gathering initial setup details...")

        apple_id = take_input("Your Apple ID: ", "APPLE_ID", True)
        password = take_input("Your Apple ID Password: ", "APPLE_ID_PASSWORD", True, True)
        target_device_model = take_input("Target Device Model: ", "TARGET_DEVICE_MODEL", True)

        sensitive_config_manager.set_value("apple_id", apple_id)
        sensitive_config_manager.set_value("password", password)
        config_manager.set_value("target_device_model", target_device_model)

        if not poll_interval_seconds_str:
            config_manager.set_value("poll_interval_seconds", poll_interval_seconds_default)  # Default value
            poll_interval_seconds_str = str(poll_interval_seconds_default)

        config_manager.save_config()
        logger.info("Initial setup complete and configuration saved.")
    else:
        logger.info("Configuration loaded from file.")

    try:
        poll_interval_seconds = int(
            poll_interval_seconds_str) if poll_interval_seconds_str else poll_interval_seconds_default
    except ValueError:
        logger.error(
            f"Invalid value of 'poll_interval_seconds' in config file. Defaulting to {poll_interval_seconds_default}",
            True)
        poll_interval_seconds = poll_interval_seconds_default

    # Return with correct type
    return_tuple = str(apple_id), str(password), str(target_device_model), int(poll_interval_seconds)
    return return_tuple


def initialize_icloud(apple_id, password) -> PyiCloudService:
    """
    Initializes and returns the authenticated iCloud service instance.

    Args:
        apple_id: The Apple ID email address
        password: The Apple ID password

    Returns:
        An authenticated PyiCloudService instance
    """
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
    """
    Initializes the alert method(s) based on configuration or user input.

    Non-tty friendly

    Returns:
        A dictionary indicating which alert methods are enabled.
    """
    alert_methods = {"Discord Webhook": False, "WhatsApp": False}
    current_method = config_manager.get_value("current_alert_method")

    if not current_method:
        if tty:
            logger.info("No alert method configured yet. Ask the user if they'd like to add one now")
            try:
                answer = input("No alert method configured. Would you like to add one now? (y/N): ").strip().lower()
            except Exception as e:
                logger.error(f"Unexpected Error: {e}. No alert methods configured")
                return alert_methods

            if answer in ("y", "yes"):
                print("Choose alert method:\n1) Discord Webhook\n2) WhatsApp\n3) Both")
                choice = input("Enter choice [1-3]: ").strip()
                if choice == "1":
                    config_manager.set_value("current_alert_method", "Discord Webhook", True)
                    alert_methods["Discord Webhook"] = True
                elif choice == "2":
                    config_manager.set_value("current_alert_method", "WhatsApp", True)
                    alert_methods["WhatsApp"] = True
                elif choice == "3":
                    config_manager.set_value("current_alert_method", "both", True)
                    for k in alert_methods:
                        alert_methods[k] = True
                else:
                    logger.warning("Invalid selection. No alert method configured.", True)
                logger.debug(f"Selected alert method: {choice}")
        else:
            choice = take_input("", "ALERT_METHOD", False).strip().lower()

            if choice == "discord webhook":
                config_manager.set_value("current_alert_method", "Discord Webhook", True)
                alert_methods["Discord Webhook"] = True
            elif choice == "whatsapp":
                config_manager.set_value("current_alert_method", "WhatsApp", True)
                alert_methods["WhatsApp"] = True
            elif choice == "both":
                config_manager.set_value("current_alert_method", "both", True)
                for k in alert_methods:
                    alert_methods[k] = True
            else:
                logger.warning(f"Invalid alert method '{choice}'. No alert method configured.", True)
            logger.debug(f"Configured alert methods: {alert_methods}")

        return alert_methods

    # TTY branch
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
    """
    Initializes the Neonize WhatsApp client, prompting for QR code scan if not already authenticated.

    Non-tty friendly

    Returns:
         WhatsAppClient instance
    """
    whatsapp_client = WhatsAppClient(NEONIZE_SESSION_FILE_PATH, config_manager, logger)

    if not NEONIZE_SESSION_FILE_PATH.exists() or not whatsapp_client.is_logged_in:
        logger.info("WhatsApp is not logged in. Setting up new connection...", True)
        print("Please scan the QR code to login to you WhatsApp account. Press enter to continue...")
        sys.stdin.readline()

        while not whatsapp_client.connected:
            whatsapp_client.connect()
            time.sleep(15)

        whatsapp_client.disconnect()
        return whatsapp_client

    return whatsapp_client


def initialize_discord_webhook(sensitive_config_manager: SensitiveConfigManager) -> str:
    """
    Retrieves the Discord webhook URL from config or prompts the user to add it if not found.

    Non-tty friendly. Uses encryption.

    Args:
        sensitive_config_manager: An instance of ``SensitiveConfigManager``

    Returns:
        The Discord webhook URL
    """
    webhook_url = sensitive_config_manager.get_value("discord_webhook")
    if webhook_url:
        return webhook_url
    else:
        logger.info("Discord Webhook URL doesn't exist. Prompting user...")
        webhook_url = take_input("Please enter your discord webhook: ", "DISCORD_WEBHOOK")
        sensitive_config_manager.set_value("discord_webhook", webhook_url)

        return webhook_url


def initialize_whatsapp_recipients(sensitive_config_manager: SensitiveConfigManager) -> list:
    """
    Retrieves WhatsApp recipient numbers from config or prompts user to add them.

    Not non-tty friendly. Uses encryption

    Args:
        sensitive_config_manager: An instance of ``SensitiveConfigManager``

    Returns:
        A list of WhatsApp recipient phone numbers (with country code, no Plus(+))
    """
    stored_recipients = sensitive_config_manager.get_value("whatsapp_recipients")

    # Try to parse existing recipients from config
    if stored_recipients:
        try:
            recipients = json.loads(stored_recipients) if isinstance(stored_recipients, str) else stored_recipients
            if isinstance(recipients, list) and len(recipients) > 0:
                logger.info(f"Found {len(recipients)} WhatsApp recipient(s) in config.")
                return recipients
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid WhatsApp recipients format in config.", True)

    # No valid recipients found, try to add them
    logger.info("No WhatsApp recipients configured. Add recipient phone numbers now.", True)
    recipients = []

    try:
        while True:
            phone = input(
                "Enter WhatsApp recipient number (country code without +, e.g., 12125551234) or 'done' to finish: ").strip()
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
            sensitive_config_manager.set_value("whatsapp_recipients", json.dumps(recipients))
            logger.info(f"Saved {len(recipients)} WhatsApp recipient(s) to config.")

    except Exception as e:
        logger.error(f"Error adding WhatsApp recipients: {e}")

    return recipients


def initialize_aes128_cipher() -> Optional[Fernet]:
    """
    Hashes the `master_password` to exactly 16 bytes, and converts it to a 32-byte URL-safe Base64 key for Fernet.

    Returns:
        Instance of Fernet with ``master_password`` as the key. None if ``master_password`` is not set.
    """
    master_password = take_input("Your master password (used for encryption): ", "MASTER_PASSWORD", False, True)

    if not master_password:
        logger.critical("No master password has been set. It is required to encrypt your sensitive data. "
                        "\nWithout encryption, all your sensitive data can be read by others who has access to the computer. "
                        "\nIt is strongly advised to set a master password for peace of mind.", True)
        return None

    # Hash the master_password using MD5 to get an exact 16-byte digest (128 bits)
    aes_128_key = hashlib.md5(master_password.encode('utf-8')).digest()

    # Fernet requires a 32-byte key format (Base64 encoded string of 32 bytes total).
    # It pads the 16-byte key using standard URL-safe Base64 mapping to satisfy Fernet's wrapper.
    fernet_key = base64.urlsafe_b64encode(aes_128_key + aes_128_key)

    return Fernet(fernet_key)


def trigger_alert(device_name,
                  device_model,
                  device_battery,
                  location_data,
                  discord_webhook,
                  whatsapp_client,
                  whatsapp_recipients,
                  disable_alert_once=False):
    """
    Executes notification protocols when a new location coordinate is captured.

    Args:
        device_name: (str) The name of the device
        device_model: (str) The model of the device
        device_battery: (int | str) Battery of the device. Default is 'Unknown'
        location_data: (dict) The location data containing latitude, longitude, and other details
        discord_webhook: (str) The Discord webhook URL
        whatsapp_client: (WhatsAppClient) The WhatsApp client instance
        whatsapp_recipients: (list) The list of WhatsApp recipient numbers
        disable_alert_once: (bool) Don't alert using any of the alert methods. Only log locally.
    """
    latitude = location_data.get("latitude")
    longitude = location_data.get("longitude")
    accuracy = location_data.get("horizontalAccuracy")  # Radius of accuracy in meters
    timestamp_ms = location_data.get("timeStamp")

    if isinstance(timestamp_ms, (int, float)):  # Validate before division to prevent potential NoneType errors
        readable_time = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %I:%M:%S %p')
    else:
        logger.warning("No timestamp found in location data. Defaulting to ;Unknown;", True)
        readable_time = "Unknown"

    maps_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

    message = (f"\n{'=' * 60}"
               f"\nALERT: {device_name}/{device_model} IS ONLINE / POSITION UPDATED"
               f"\nTimestamp: {readable_time}"
               f"\nBattery: {device_battery}%"
               f"\nCoordinates: {latitude}, {longitude}"
               f"\nAccuracy  : Within {round(accuracy, 2)} meters"
               f"\nGoogle Maps Link: {maps_url}"
               f"\n{'=' * 60}\n")
    logger.info(message, True)

    if disable_alert_once:
        return

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
    """
    Entry point of the script
    """
    # Initialize encryption and sensitive data manager
    cipher_suite = initialize_aes128_cipher()
    if not cipher_suite:
        logger.warning("Encryption is disabled.", True)
    sensitive_config_manager = SensitiveConfigManager(cipher_suite, config_manager, logger, service_name)

    # Update the configs with environment variables
    update_config_with_env(sensitive_config_manager)

    # Initialize the whole script
    apple_id, password, target_device_model, poll_interval_seconds = initialize(sensitive_config_manager)
    alert_methods = initialize_alert_method()
    discord_webhook = None
    whatsapp_client = None
    whatsapp_recipients = []

    if alert_methods["Discord Webhook"]:
        discord_webhook = initialize_discord_webhook(sensitive_config_manager)
    if alert_methods["WhatsApp"]:
        whatsapp_client = initialize_neonize()
        whatsapp_recipients = initialize_whatsapp_recipients(sensitive_config_manager)

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
                device_battery = status.get("batteryLevel", "Unknown")

                # Normalize device_battery
                try:
                    logger.debug(f"Raw battery: {device_battery}")
                    device_battery = round(device_battery * 100)
                except TypeError:
                    logger.warning(f"Invalid device battery: {device_battery}. Defaulting to 'Unknown.'")
                    device_battery = "Unknown"

                # Only advance if device model matches
                if target_device_model.lower() in device_model.lower():
                    location = device.location
                    logger.debug(f"Raw location: {location}")

                    if location:
                        timestamp_ms = location.get("timeStamp")
                        current_time = datetime.now()

                        # Determine if the location update is recent enough to alert (default to True if unknown)
                        is_recent = True
                        if isinstance(timestamp_ms, (int, float)):
                            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
                            is_recent = (current_time - timestamp) < timedelta(minutes=30)

                        # Only trigger alerts if it's a completely new location update
                        if timestamp_ms != last_known_timestamp:
                            last_known_timestamp = timestamp_ms
                            if is_recent:
                                trigger_alert(device_name, device_model, device_battery, location, discord_webhook,
                                              whatsapp_client, whatsapp_recipients)
                            else:
                                logger.info("Location changed but data is 30 minutes older. Logging location locally.",
                                            True)
                                trigger_alert(device_name, device_model, device_battery, location, discord_webhook,
                                              whatsapp_client, whatsapp_recipients, True)
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
    main()
