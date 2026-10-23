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

## 目前雲端部署（Vercel＋Supabase）

- 網址：https://tpmr-lesson-plan.vercel.app （Vercel 專案 `tpmr-lesson-plan`，函式區域 hnd1 東京）
- 資料庫：Supabase 專案 `bt-lesson-plan`（ap-northeast-1 東京，免費方案），資料表在 `btapp` schema，不經 Supabase 公開 API；應用程式以專用角色 `bt_app` 經連線池（transaction mode）連線。
- 程式碼來源：GitHub `popmusictw-boop/Dv-game` 的獨立分支 `bt-lesson-plan`（不含學生資料與金鑰）。
- 環境變數（Vercel，已設為 sensitive）：`BT_SECRET_KEY`、`BT_DATA_KEY`、`BT_DATABASE_URL`；另有 `BT_ENV=production`、`BT_SESSION_SECURE=1`、`BT_MAX_UPLOAD_MB=4`、`BT_INSTANCE_DIR=/tmp/bt`。
- 雲端限制：單檔上傳上限 4 MB（Vercel 請求大小限制）；無 OCR（掃描檔請改用文字型 PDF／Word 或貼上文字）；PDF 改由預覽頁「列印／另存 PDF」產生。
- 資料庫連線以 Supabase Root 2021 CA（`btsys/certs/supabase-ca.pem`，SHA-256 指紋與 Dashboard 憑證一致）完整驗證伺服器憑證。
- 更新部署：推送到 `bt-lesson-plan` 分支後，在 Vercel 對該分支建立 Production 部署。
- 資料保存：系統不長期保存資料。前一天（臺灣時間）建立的教案（含學生姓名、能力分析、生成內容）與所有上傳檔案於隔日自動刪除（Vercel 排程每日 00:05 臺灣時間執行 `/api/cron/purge`，並在系統有人使用時每 10 分鐘檢查一次）。排程以環境變數 `CRON_SECRET` 驗證。
