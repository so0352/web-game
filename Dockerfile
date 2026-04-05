FROM node:20-bookworm-slim AS socketio-client

WORKDIR /tmp/socketio-client
RUN npm install --omit=dev socket.io-client@4.7.5 \
    && cp node_modules/socket.io-client/dist/socket.io.min.js /socket.io.min.js

# Pythonベースイメージを使用
FROM python:3.11-slim-bookworm

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係をインストール
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY backend/ ./backend/
COPY --from=socketio-client /socket.io.min.js ./backend/static/vendor/socket.io.min.js

# ポートを公開
EXPOSE 5000

# 環境変数を設定
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

# アプリケーションを起動
CMD ["python3", "backend/app.py"]
