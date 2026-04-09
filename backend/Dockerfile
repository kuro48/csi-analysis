FROM python:3.11-slim

# 作業ディレクトリ設定
WORKDIR /app

# システム依存関係をインストール（Node.js 18、Rust、circom用）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        gfortran \
        python3-dev \
        libpq-dev \
        libopenblas-dev \
        liblapack-dev \
        postgresql-client \
        curl \
        wget \
        build-essential \
        libssl-dev \
        pkg-config \
        git \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# Node.js 18をインストール
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Rustをインストール（circomビルド用）
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# circomをインストール
RUN git clone https://github.com/iden3/circom.git /tmp/circom \
    && cd /tmp/circom \
    && cargo build --release \
    && cp target/release/circom /usr/local/bin/

# snarkjsをグローバルインストール
RUN npm install -g snarkjs@0.7.4

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
