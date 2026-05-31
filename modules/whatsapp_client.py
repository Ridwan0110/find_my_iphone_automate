# Imports
import time
import threading
from redu_config_manager import ConfigManager
from redu_logger import RemoteLogger
from pathlib import Path
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv
from neonize.utils import build_jid


class WhatsAppClient:
    """
    A wrapper around the Neonize WhatsApp client to manage connection state, event handling, and message sending with thread safety and auto-reconnect capabilities.
    Core capability is to stay connected with WhatsApp servers via threading while interacting with the client.
    """

    def __init__(self, session_path: Path, config_manager: ConfigManager, logger: RemoteLogger):
        """
        Initializes the WhatsApp client, setting up event handlers and internal state.

        Args:
            session_path: Path to the WhatsApp session file for storing authentication data
            config_manager: An instance of ConfigManager for managing configuration values
            logger: An instance of RemoteLogger to log data
        """
        self.session_path = session_path
        self.config_manager = config_manager
        self.logger = logger
        self.logger.info("Initializing WhatsAppClient...")

        self.class_name = "WhatsAppClient"
        self.client = NewClient(str(session_path))
        self._lock = threading.Lock()
        self._is_connecting = False
        self._connected = False
        self._is_logged_in = self._retrieve_login_status()
        self._qr_showed = False
        self.whatsapp_thread = None

        @self.client.qr
        def on_qr(client, qr_bytes: bytes):
            self.logger.info(f"[{self.class_name}] QR Code intercepted")
            self._qr_showed = True
            self.client.event._Event__onqr(client, qr_bytes)

        self.client.event(ConnectedEv)(self._on_connected)
        self.client.event(DisconnectedEv)(self._on_disconnect)
        self.client.event(LoggedOutEv)(self._on_log_out)
        self.logger.info("Initialized WhatsAppClient")

    def _update_login_status(self, status: bool):
        """
        Updates the login status both in memory and in the config file.

        Args:
            status: The new login status to set
        """
        self._is_logged_in = status
        self.config_manager.set_value("is_neonize_logged_in", str(status), True)
        self.logger.info(f"[{self.class_name}] Updated login status: {status}")

    def _retrieve_login_status(self) -> bool:
        """
        Retrieves the login status from the config file.

        Returns:
            The login status as a boolean
        """
        status = str(self.config_manager.get_value("is_neonize_logged_in")).strip().lower() == "true"
        self.logger.info(f"[{self.class_name}] Retrieved login status: {status}")

        return status

    def _update_connection_flags(self, connected: bool, is_connecting: bool):
        """
        Updates the connection state flags. It is highly recommended to call it with thread lock acquired to ensure thread safety.

        Args:
            connected: Whether the client is currently connected
            is_connecting: Whether a connection attempt is currently in progress
        """
        self._connected = connected
        self._is_connecting = is_connecting

    def _do_connect(self):
        """
        Handles the actual connection logic in a separate thread, including error handling and state updates.
        """
        try:
            self.logger.info(f"[{self.class_name}] Connecting...", True)
            self.client.connect()
        except Exception as e:
            self.logger.error(f"[{self.class_name}] Failed to connect: {e}", True)
        finally:
            with self._lock:
                self._update_connection_flags(False, False)

    def _on_connected(self, cl, event):
        """
        Event handler for when the WhatsApp client successfully connects to the server. Updates connection and login status accordingly.

        Args:
            cl: The client instance that triggered the event
            event: The event object containing details about the connection event
        """
        self.logger.info(f"[{self.class_name}] Connected", True)
        with self._lock:
            self._update_connection_flags(True, False)
            self._update_login_status(True)

    def _on_disconnect(self, cl, event):
        """
        Event handler for when the WhatsApp client disconnects from the server. Updates connection and login status accordingly.

        Args:
            cl: The client instance that triggered the event
            event: The event object containing details about the connection event
        """
        self.logger.info(f"[{self.class_name}] Disconnected")
        with self._lock:
            self._update_connection_flags(False, False)

    def _on_log_out(self, cl, event):
        """
        Event handler for when the WhatsApp client logs out of the server. Updates connection and login status accordingly.

        Args:
            cl: The client instance that triggered the event
            event: The event object containing details about the connection event
        """
        self.logger.warning(f"[{self.class_name}] Logged out")
        with self._lock:
            self._update_login_status(False)

    def _auto_connect(self, timeout: int, retry_count: int) -> bool:
        """
        Attempts to auto-connect the WhatsApp client with retries and timeout.

        Args:
            timeout: The maximum time to wait for a connection attempt to succeed before retrying
            retry_count: The number of times to retry the connection attempt if it fails

        Returns:
            True if the client successfully connected, False otherwise
        """
        self.logger.info(f"[{self.class_name}] Auto-connecting...", True)
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
                self.logger.warning(
                    f"[{self.class_name}] Auto-connect attempt {try_count}/{max_tries} failed. Retrying...",
                    True
                )

        # Final check after all attempts are exhausted
        if not self._connected:
            self.logger.warning(f"[{self.class_name}] Auto-connect failed after {max_tries} attempts", True)
            return False
        return True

    @property
    def connected(self) -> bool:
        """
        Returns whether the WhatsApp client is currently connected to the server.

        Returns:
            True if connected, False otherwise
        """
        with self._lock:
            return self._connected

    @property
    def is_logged_in(self):
        """
        Returns whether the WhatsApp client is currently logged in. This is a separate state from just being connected, as the client may be connected but not authenticated.

        Returns:
            True if logged in, False otherwise
        """
        with self._lock:
            return self._is_logged_in

    @property
    def qr_showed(self) -> bool:
        """
        Returns whether the QR code has been shown during this session. This can be used to determine if the user has been prompted to scan the QR code for authentication.

        Returns:
            True if the QR code has been shown, False otherwise
        """
        with self._lock:
            return self._qr_showed

    def connect(self):
        """
        Initiates the connection process to the WhatsApp servers in a separate thread. If already connected or in the process of connecting, it will log that information and return immediately.
        """
        with self._lock:
            if self._connected or self._is_connecting:
                self.logger.info(f"[{self.class_name}] Already connected or connecting", True)
                return
            self._is_connecting = True

        self.whatsapp_thread = threading.Thread(target=self._do_connect, daemon=True)
        self.whatsapp_thread.start()

    def disconnect(self, timeout: int = 30):
        """
        Disconnects from the WhatsApp servers and waits for the connection thread to finish.

        Args:
            timeout: The maximum time to wait for the connection thread to finish after initiating disconnect
        """
        with self._lock:
            if not self._connected and not self._is_connecting:
                self.logger.info(f"[{self.class_name}] Already disconnected", True)
                return
            self.logger.info(f"[{self.class_name}] Disconnecting...")
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
            True if send was attempted, False if client unavailable
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
            self.logger.info(f"[{self.class_name}] Message sent to {recipient}", True)
            return True
        except Exception as e:
            self.logger.error(f"[{self.class_name}] Couldn't sent message to {recipient}: {e}", True)
            return False
