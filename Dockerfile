# 北特教案生成系統：含 OCR（繁中）、LibreOffice（PDF 轉檔）、中文字型
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BT_ENV=production BT_INSTANCE_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-eng \
      libreoffice-writer-nogui fonts-noto-cjk fonts-arphic-ukai \
    && rm -rf /var/lib/apt/lists/*
# 若學校持有標楷體授權，將 kaiu.ttf 放在 fonts/ 目錄即可讓 PDF 字型與 Word 一致
COPY fonts/ /usr/share/fonts/truetype/school/
RUN fc-cache -f >/dev/null || true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.*
COPY . .
RUN useradd -r -u 1001 bt && mkdir -p /data && chown -R bt /data
USER bt
VOLUME ["/data"]
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-t", "180", "-b", "0.0.0.0:8000", "wsgi:app"]
