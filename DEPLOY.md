# 安裝部署說明

## 建議：Docker（含繁中 OCR、LibreOffice、中文字型）

1. 準備金鑰並建立 `.env`（參考 `.env.example`）：
   ```bash
   python -c "import secrets;print(secrets.token_hex(32))"                              # BT_SECRET_KEY
   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # BT_DATA_KEY
   ```
   `BT_DATA_KEY` 用來加密所有學生資料，**遺失即無法解密**；請另行安全備份，且不要與資料庫放在同一處。
2. （選用）把學校授權的標楷體 `kaiu.ttf` 放入 `fonts/`。
3. 建置與啟動：`docker compose up -d --build`
4. 建立管理者帳號：`docker compose exec btlesson python manage.py create-user admin 系統管理者 --admin`
5. 由學校反向代理（Nginx／IIS）以 HTTPS 對外，轉到 `127.0.0.1:8000`，並設 `BT_SESSION_SECURE=1`。建議只開放校內網路或 VPN。
6. 排程清除逾期資料（每日）：`docker compose exec btlesson flask --app wsgi purge-old`

## 不使用 Docker（Linux）

```bash
sudo apt install python3-venv tesseract-ocr tesseract-ocr-chi-tra libreoffice-writer fonts-noto-cjk fonts-arphic-ukai
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt gunicorn
export $(grep -v '^#' .env | xargs)
python manage.py create-user admin 系統管理者 --admin
gunicorn -w 2 -t 180 -b 127.0.0.1:8000 wsgi:app
```

Windows 伺服器：安裝 Python 3.11+、Tesseract（勾選 Chinese Traditional）、LibreOffice，並設定 `BT_SOFFICE` 指向 `soffice.exe`。

## 備份與還原

備份 `/data`（Docker volume `btdata`：資料庫與加密檔案）與 `BT_DATA_KEY`。兩者缺一無法還原。

## 開啟外部 AI（選用）

確認學校／主管機關同意學生資料（以代號取代姓名）送至外部服務後，於 `.env` 設定 `BT_AI_ENABLED=1`、`ANTHROPIC_API_KEY=...` 並重新啟動。金鑰只存在伺服器端。

## 測試

```bash
python -m unittest discover -s tests -v
pip install playwright && playwright install chromium
python tests/ui_flow.py https://你的網址 帳號 密碼 /tmp/out mobile
```
