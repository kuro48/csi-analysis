FROM node:20-alpine

# 作業ディレクトリ設定
WORKDIR /app

# パッケージファイルをコピー
COPY package*.json ./

# 依存関係をインストール
RUN npm ci --legacy-peer-deps

# アプリケーションコードをコピー
COPY . .

# Next.jsアプリケーションをビルド（本番環境用）
# 開発環境では次の行をコメントアウト
# RUN npm run build

# ポート公開
EXPOSE 3000

# 環境変数設定
ENV NODE_ENV=development
ENV NEXT_TELEMETRY_DISABLED=1

# 開発サーバー起動（本番環境では npm start に変更）
CMD ["npm", "run", "dev"]