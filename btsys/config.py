"""系統設定：一律由環境變數讀取，金鑰不寫入程式碼或前端。"""
import os, secrets, pathlib
from cryptography.fernet import Fernet

BASE = pathlib.Path(__file__).resolve().parent.parent
INSTANCE = pathlib.Path(os.environ.get('BT_INSTANCE_DIR', BASE / 'instance'))
INSTANCE.mkdir(parents=True, exist_ok=True)

def _persisted_secret(name, factory):
    """開發環境若未設定金鑰，於 instance/ 產生並保存（權限 600）；正式環境請以環境變數提供。"""
    p = INSTANCE / name
    if p.exists():
        return p.read_text().strip()
    v = factory()
    p.write_text(v)
    try: os.chmod(p, 0o600)
    except OSError: pass
    return v

class Config:
    ENV = os.environ.get('BT_ENV', 'development')
    SECRET_KEY = os.environ.get('BT_SECRET_KEY') or _persisted_secret('.secret_key', lambda: secrets.token_hex(32))
    # 學生檔案、擷取文字與草稿內容一律以此金鑰加密保存（Fernet / AES-128-CBC + HMAC）
    DATA_KEY = os.environ.get('BT_DATA_KEY') or _persisted_secret('.data_key', lambda: Fernet.generate_key().decode())
    DATABASE = os.environ.get('BT_DATABASE_URL') or os.environ.get('BT_DATABASE', str(INSTANCE / 'btlesson.sqlite3'))
    UPLOAD_DIR = os.environ.get('BT_UPLOAD_DIR', str(INSTANCE / 'uploads'))
    MAX_UPLOAD_MB = int(os.environ.get('BT_MAX_UPLOAD_MB', '20'))
    RETENTION_DAYS = int(os.environ.get('BT_RETENTION_DAYS', '365'))
    SESSION_SECURE = os.environ.get('BT_SESSION_SECURE', '0') == '1'
    SESSION_HOURS = int(os.environ.get('BT_SESSION_HOURS', '8'))
    # AI：金鑰只在伺服器端；未設定時系統只使用本機規則式擷取
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    AI_MODEL = os.environ.get('BT_AI_MODEL', 'claude-sonnet-5-5')
    AI_ENABLED = os.environ.get('BT_AI_ENABLED', '0') == '1' and bool(os.environ.get('ANTHROPIC_API_KEY'))
    SOFFICE = os.environ.get('BT_SOFFICE', 'soffice')
    OCR_LANG = os.environ.get('BT_OCR_LANG', 'chi_tra+eng')
    SCHOOL_NAME = '臺北市立臺北特殊教育學校'
    CURRICULUM_DIR = str(BASE / 'data' / 'curriculum')
