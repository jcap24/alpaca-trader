"""Security utilities for encryption, password hashing, and 2FA."""
import logging
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

import pyotp
import qrcode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from io import BytesIO
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger("alpaca_trader")


class EncryptionManager:
    """Manages encryption/decryption of sensitive data like API keys."""

    def __init__(self, master_key: str = None):
        """
        Initialize encryption manager with a master key.

        Args:
            master_key: Master encryption key (from environment variable).
                       If None, will attempt to load from ENCRYPTION_KEY env var.
        """
        if master_key is None:
            master_key = os.getenv("ENCRYPTION_KEY")

        if not master_key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable not set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Derive a Fernet key from the master key
        self.fernet = self._create_fernet(master_key)

    def _create_fernet(self, master_key: str) -> Fernet:
        """Create a Fernet cipher from the master key."""
        # Use PBKDF2HMAC to derive a proper 32-byte key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"alpaca_trader_salt",  # In production, use random salt per installation
            iterations=100000,
        )
        key = urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return base64-encoded ciphertext."""
        if not plaintext:
            return ""
        encrypted = self.fernet.encrypt(plaintext.encode())
        return urlsafe_b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext and return plaintext string."""
        if not ciphertext:
            return ""
        try:
            decoded = urlsafe_b64decode(ciphertext.encode())
            decrypted = self.fernet.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError("Failed to decrypt data. Invalid encryption key or corrupted data.")

    @staticmethod
    def is_encrypted(value: str) -> bool:
        """Check if a value appears to be encrypted (heuristic check)."""
        if not value:
            return False
        # Encrypted values are base64-encoded and typically longer
        try:
            urlsafe_b64decode(value.encode())
            return len(value) > 50  # Encrypted values are typically longer
        except Exception:
            return False


class PasswordManager:
    """Manages password hashing and verification."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using Werkzeug's secure method (pbkdf2:sha256)."""
        return generate_password_hash(password, method="pbkdf2:sha256")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return check_password_hash(password_hash, password)


class TwoFactorAuth:
    """Manages two-factor authentication (TOTP)."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def generate_qr_code(secret: str, username: str, issuer: str = "Alpaca Trader") -> BytesIO:
        """
        Generate a QR code for the TOTP secret.

        Args:
            secret: The TOTP secret
            username: Username for the account
            issuer: Issuer name (app name)

        Returns:
            BytesIO object containing the QR code PNG image
        """
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=username, issuer_name=issuer
        )

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def verify_totp(secret: str, token: str) -> bool:
        """
        Verify a TOTP token.

        Args:
            secret: The TOTP secret
            token: The 6-digit token from user's authenticator app

        Returns:
            True if token is valid, False otherwise
        """
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)  # Allow 1 time step tolerance


def generate_encryption_key() -> str:
    """Generate a new encryption key for ENCRYPTION_KEY env variable."""
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    # Utility to generate a new encryption key
    print("Generated Encryption Key:")
    print(generate_encryption_key())
    print("\nAdd this to your .env file as:")
    print("ENCRYPTION_KEY=<key_above>")
