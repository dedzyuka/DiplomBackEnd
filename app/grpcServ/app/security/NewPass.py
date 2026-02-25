import hashlib
import os
import secrets


class CreatePass:
    @staticmethod
    def createSalt() -> bytes:
        return os.urandom(16)

    @staticmethod
    def saltStrToBytes(salt: str) -> bytes:
        return bytes.fromhex(salt)

    @staticmethod
    def createPassWithSalt(password: str):
        saltBytes = CreatePass.createSalt()
        hash_bytes = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            saltBytes,
            600000,
        )
        result_hash = hash_bytes.hex()
        salt = saltBytes.hex()
        return result_hash, salt

    @staticmethod
    def VerifyPass(password: str, salt: str, db_hash_pass: str) -> bool:
        saltBytes = CreatePass.saltStrToBytes(salt)
        hash_passChek = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            saltBytes,
            600000,
        )
        return secrets.compare_digest(db_hash_pass, hash_passChek.hex())