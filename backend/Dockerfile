FROM python:3.11-slim

# 作業ディレクトリ設定
WORKDIR /app

# システム依存関係をインストール
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# エントリーポイントスクリプトをコピーして実行権限を付与
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# アップロード用ディレクトリ作成
RUN mkdir -p /app/uploads

# ポート公開
EXPOSE 8000

# ヘルスチェック用エンドポイントの確認
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 環境変数設定
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# エントリーポイントを設定
ENTRYPOINT ["/entrypoint.sh"]