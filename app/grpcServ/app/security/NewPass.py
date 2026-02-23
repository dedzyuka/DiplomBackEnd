import os
import hashlib
import secrets

class CreatePass:
    @staticmethod
    def createSalt()->bytes:
        return os.urandom(16)
        # salt_hex = salt.hex()
    @staticmethod
    def saltStrToBytes(salt:str)->bytes:
        return bytes.fromhex(salt)
    @staticmethod
    def createPassWithSalt(password:str):
        saltBytes = CreatePass.createSalt()
        # password_hash = password.
        hash_bytes = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        saltBytes, 
        600000
        )
        result_hash = hash_bytes.hex()
        salt = saltBytes.hex()
        print(result_hash)
        print(salt)
        return result_hash, salt
    @staticmethod
    def VerifyPass(password: str, salt:str, db_hash_pass):
        saltBytes = CreatePass.saltStrToBytes(salt) 
        hash_passChek = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        saltBytes, 
        600000
        )
        if secrets.compare_digest(db_hash_pass, hash_passChek.hex()):
            print("Пароль верный")
        else:
            print("Доступ запрещен")

# password = "яебанат"
# a , b = CreatePass.createPassWithSalt(password)
# print(f"1-{a}, 2 - {b}")

# res = CreatePass.VerifyPass(password="яебанат", salt = b, db_hash_pass=a)