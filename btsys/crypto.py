import json
from cryptography.fernet import Fernet
from flask import current_app

def _f():
    return Fernet(current_app.config['DATA_KEY'].encode())

def enc_bytes(b: bytes) -> bytes: return _f().encrypt(b)
def dec_bytes(b: bytes) -> bytes: return _f().decrypt(b)
def enc_json(o) -> bytes: return enc_bytes(json.dumps(o, ensure_ascii=False).encode())
def dec_json(b):
    return None if b is None else json.loads(dec_bytes(b).decode())
def enc_text(s: str) -> bytes: return enc_bytes(s.encode())
def dec_text(b) -> str: return dec_bytes(b).decode()
