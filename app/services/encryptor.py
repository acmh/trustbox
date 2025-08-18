# app/services/encryptor.py
import base64
import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class Encryptor:
    def __init__(self, public_key: str, salt: bytes | None = None):
        self.public_key = bytes(public_key, "utf-8")
        self.salt = salt if salt is not None else os.urandom(16)
        self.key = self.generate_key()
        self.fernet = Fernet(self.key)

    def generate_key(self):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=1_200_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(self.public_key))
    
    def encrypt(self, data):
        return self.fernet.encrypt(data)
    
    def decrypt(self, data):
        return self.fernet.decrypt(data)
    
    def get_salt(self):
        return self.salt
    
    def get_key(self):
        return self.key
