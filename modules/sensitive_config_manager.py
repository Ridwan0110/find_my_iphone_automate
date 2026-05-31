# Imports
import keyring
from redu_config_manager import ConfigManager
from redu_logger import RemoteLogger
from keyring.errors import KeyringError
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional


class SensitiveConfigManager:
    """
    Securely manages sensitive configs
    """

    def __init__(self, cipher_suite: Optional[Fernet], config_manager: ConfigManager, logger: RemoteLogger, service_name: str):
        """
        Initializes the class

        Args:
            cipher_suite: A ``Fernet`` instance
            config_manager: An ``ConfigManager`` instance
            logger: An instance of RemoteLogger to log data
            service_name: (str) String of service name to use in keyring
        """
        self.cipher_suite = cipher_suite
        self.config_manager = config_manager
        self.logger = logger
        self.service_name = service_name

    def set_value(self, key: str, value: str) -> bool:
        """
        Encrypts (if cipher available) and stores value in keyring or fallback to config file.

        Args:
            key: (str) Key to store as
            value: (str) Value of the key

        Returns:
            True if success, False otherwise
        """
        final_value = value

        if isinstance(self.cipher_suite, Fernet):
            encrypted = self._encrypt_value(value)
            if encrypted is None:
                self.logger.error(f"Aborting save for '{key}' to prevent storing sensitive data in plaintext.", True)
                return False
            final_value = encrypted

        success = self._keyring_set_credential(key, final_value)

        # Fallback to config file
        if not success:
            self.logger.warning(f"Keyring failed. Saving '{key}' to local configuration fallback.", True)
            self.config_manager.set_value(key, final_value, True)

        self.logger.info(f"Successfully saved value for key '{key}'.")
        return True

    def get_value(self, key: str) -> Optional[str]:
        """
        Retrieves and decrypts value from keyring, or fallback to config file.

        Args:
            key: (str) Key to retrieve

        Returns:
            If found, value of the key, None otherwise
        """
        value = self._keyring_get_credential(key)

        # Fallback to config file
        if not value:
            value = self.config_manager.get_value(key)

        # If neither had the config, exit early
        if not value:
            self.logger.warning(f"Key '{key}' not found in both system keyring and config file.", True)
            return None

        if isinstance(self.cipher_suite, Fernet):
            return self._decrypt_value(value)

        self.logger.info(f"Successfully retrieved value for key '{key}'.")
        return value

    def _encrypt_value(self, value) -> Optional[str]:
        try:
            encrypted_bytes = self.cipher_suite.encrypt(value.encode('utf-8'))
            encrypted_string = encrypted_bytes.decode('utf-8')
            self.logger.info(f"Successfully encrypted value.")

            return encrypted_string
        except TypeError as e:
            self.logger.error(f"Failed to encrypt data: {e}", True)
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", True)
            return None

    def _decrypt_value(self, value) -> Optional[str]:
        try:
            decrypted_bytes = self.cipher_suite.decrypt(value.encode('utf-8'))
            decrypted_string = decrypted_bytes.decode('utf-8')
            return decrypted_string
        except InvalidToken as e:
            self.logger.error(f"Failed to decrypt value. The value is invalid, tampered with, or expired.", True)
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", True)
            return None

    def _keyring_set_credential(self, username: str, credential_string: str) -> bool:
        """
        Saves a credential to the keyring.

        Args:
            username: (str) The username for the credentials
            credential_string: (str) The credential string to store

        Returns:
            True if success, False otherwise
        """
        try:
            keyring.set_password(self.service_name, username, credential_string)
            self.logger.info(f"Successfully saved credentials in keyring for '{username}'.")
            return True
        except KeyringError as e:
            self.logger.error(f"Failed to save to keyring: {e}", True)
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", True)
            return False

    def _keyring_get_credential(self, username) -> Optional[str]:
        """
        Retrieves a credential from the keyring.

        Args:
            username: (str) The username for the credentials

        Returns:
            A string of the decrypted credential if found, None otherwise.
        """
        try:
            credential_string = keyring.get_password(self.service_name, username)
            if not credential_string:
                self.logger.warning(f"No credentials found for '{self.service_name}' with username '{username}'")
                return None

            return credential_string
        except KeyringError as e:
            self.logger.error(f"Failed to retrieve credential from the keyring: {e}", True)
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", True)
            return None
