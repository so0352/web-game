# Webゲーム（オセロ / 将棋）

Flask + Socket.IO で動く、ブラウザ向けの対戦ゲームアプリです。
1人プレイ（AI対戦）とマルチプレイ（合言葉マッチング）の両方に対応しています。
このリポジトリは、AI agent の動作テスト兼学習を目的として作成・運用しています。
## できること
- オセロ: 人間 vs 人間 / 人間 vs AI
- 将棋: 人間 vs 人間 / 人間 vs AI
- リアルタイム対戦: Socket.IO で盤面を同期
- AI設定: エンジン切り替え、難易度・探索パラメータ調整
- Docker公開: Caddy 経由で HTTPS 終端
- モバイル対応: 小画面レイアウト最適化

## クイックスタート（Docker 推奨）

### 1. 起動
```bash
docker compose up --build
```

### 2. アクセス
- ローカル確認: https://localhost
- 公開時: https://<PUBLIC_DOMAIN>

### 3. 停止
```bash
docker compose down
```

## 公開サーバーで使う

1. `.env.example` を `.env` にコピー
2. `PUBLIC_DOMAIN` と `SECRET_KEY` を本番値に変更
3. DNS でドメインをサーバーに向ける
4. 80/443 を開放
5. `docker compose up -d --build` で起動

Caddy が証明書を自動取得し、HTTPS 配信します。

## ゲームモード

### オセロ
- 一人プレイ（AI対戦）
	- 手番を選択: 先手（黒）/ 後手（白）
	- AIエンジンを選択: `minmax` / `mcts`
	- パラメータ調整:
		- `minmax`: 探索深さ（depth）
		- `mcts`: 試行回数（iterations）
- マルチプレイ（人間同士）
	- プレイヤー名 + 合言葉を入力してマッチング
	- 同じ合言葉の相手とペア成立後に先手/後手を選択

### 将棋
- 一人プレイ（AI対戦）
	- 手番を選択: 先手 / 後手
	- AIエンジンを選択: `rule_based` / `minimax` / `mcts` / `ml`（= onnx）
	- 難易度選択: `easy` / `medium` / `hard`
	- ゲーム中でも AI 設定反映が可能
- マルチプレイ（人間同士）
	- プレイヤー名 + 合言葉でマッチング

## マルチプレイ仕様

- イベント: `start_matchmaking` / `cancel_matchmaking` / `choose_role_after_match`
- 合言葉はハッシュ化して照合（平文保存しない）
- 役割選択タイムアウト: 15秒
- 再接続猶予: 30秒
- マルチプレイ中は AI 設定を変更不可

## 実行構成（Docker）

- アプリ: Flask-SocketIO（内部 5000）
- リバースプロキシ: Caddy（外部 80/443）
- クライアント Socket.IO: `backend/static/vendor/socket.io.min.js` を同梱
- 証明書/設定の永続化: `caddy_data`, `caddy_config` ボリューム

## 環境変数

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `PUBLIC_DOMAIN` | `localhost` | Caddy の公開ホスト名 |
| `SECRET_KEY` | `othello-secret-key` | Flask セッション秘密鍵（本番は必ず変更） |
| `FLASK_DEBUG` | `0` | デバッグモード（開発のみ `1`） |
| `PORT` | `5000` | Flask-SocketIO 待受ポート |
| `SOCKETIO_CORS_ALLOWED_ORIGINS` | `http://localhost:5000,http://127.0.0.1:5000` | Socket.IO CORS 許可オリジン（CSV） |
| `APP_ENV` | 空文字 | `production` で本番ガードを有効化 |
| `MATCH_PASSWORD_PEPPER` | `SECRET_KEY` の値 | マッチング合言葉ハッシュ用キー |

補足:
- `APP_ENV=production` で `SECRET_KEY` がデフォルト値のままだと起動時にエラーになります。
- `APP_ENV=production` で `SOCKETIO_CORS_ALLOWED_ORIGINS=*` は禁止です。

## ローカル開発（Python 直実行）

Docker を使わず実行する場合の最小手順です。

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

注意:
- テンプレートは `static/vendor/socket.io.min.js` を参照します。Docker ビルドを通さない場合は同ファイルを用意してください。

## テスト

```bash
python3 -m unittest discover -s backend/tests
```

主なテスト対象:
- オセロ/将棋ロジック
- AI 手生成（将棋）
- マルチプレイのモード制約・手番制約
- 切断時クリーンアップ
- セキュリティ強化（パスワード・権限）

## 将棋AI（ML Policy / ONNX）モデル作成

将棋の `ml` / `onnx` エンジンを使う場合、学習と ONNX 書き出しを 1 回実行してください。

```bash
cd backend
python3 -m ml.train_policy --games 30 --max-plies 80 --teacher-depth 2
python3 -m ml.export_onnx --weights models/shogi_policy_weights.npz --output models/shogi_policy.onnx
```

出力先:
- `backend/models/shogi_policy_weights.npz`
- `backend/models/shogi_policy_meta.json`
- `backend/models/shogi_policy.onnx`

モデル未配置時は、`ml` / `onnx` 選択時でも安全に Minimax へフォールバックします。

詳細は `docs/shogi-ml-guide.md` を参照してください。

## ファイル構成（主要部分）

```text
web-game/
├── backend/
│   ├── app.py
│   ├── game_logic.py
│   ├── shogi_logic.py
│   ├── shogi_ai.py
│   ├── shogi_ml_features.py
│   ├── game_store.py
│   ├── handlers/
│   │   ├── game_handlers.py
│   │   ├── move_handlers.py
│   │   ├── ai_handlers.py
│   │   ├── ai_params.py
│   │   ├── matchmaking_handlers.py
│   │   └── shogi_ai_support.py
│   ├── templates/
│   ├── static/
│   ├── ml/
│   ├── models/
│   └── tests/
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
├── docs/
└── README.md
```

## 既知の制約

- ゲーム状態・マッチメイキング状態はメモリ保持のため、再起動で消えます。
- 複数インスタンス前提の共有ストレージ/共有セッションは未対応です。
- Socket.IO（WebSocket）接続が必須です。
- HTTPS 終端は Caddy 前提です（別プロキシを使う場合は構成変更が必要）。

## 関連ドキュメント

- 公開手順（GCP VM）: `docs/gcp-vm-deploy.md`
- 将棋ML手順: `docs/shogi-ml-guide.md`
