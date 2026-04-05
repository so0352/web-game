# Webゲーム（オセロ / 将棋）

Flask + Socket.IO で動作するオセロ/将棋アプリです。DockerコンテナでもローカルPythonでも起動できます。

このリポジトリは、AI agent の動作テストを目的として作成・運用しています。

## 特徴
- リアルタイム対戦機能（Socket.IO）
- オセロ（AI設定対応）と将棋（手動対戦対応）
- Dockerコンテナで起動可能
- スマートフォン対応レスポンシブUI

## 必要条件
- DockerとDocker Compose
- 外部公開する場合は独自ドメインと 80/443 の到達性

## 使い方

### Dockerを使用する場合（推奨）

1. プロジェクトディレクトリで以下を実行：

```bash
docker compose up --build
```

2. ブラウザで https://localhost にアクセス

### 公開サーバーで使う場合

1. `.env.example` を `.env` にコピーし、`PUBLIC_DOMAIN` と `SECRET_KEY` を設定してください。
2. `SECRET_KEY` は本番用の十分長い値に置き換えてください。
3. `docker compose up -d --build` で起動します。
4. DNS でドメインをサーバーに向け、80/443 を開放してください。
5. Caddy が証明書を取得し、HTTPS で公開されます。

### Dockerを使わない場合

この構成は Docker 公開を前提にしています。ローカル Python 実行も可能ですが、Socket.IO クライアントは Docker ビルド時に同梱されるため、同じ静的ファイルを別途用意する必要があります。

## Docker公開構成

このリポジトリは Docker のみで公開できる構成にしています。

- アプリ本体: Flask-SocketIO が 5000 番で待ち受け
- HTTPS 終端: Caddy が 80/443 を受けてアプリへリバースプロキシ
- Socket.IO: 同一オリジン接続を使うため、ブラウザ側の URL 指定は不要
- Socket.IO クライアント JS は Docker ビルド時に同梱されるため、実行時の CDN 依存はありません

### 環境変数

- `PUBLIC_DOMAIN`: 公開するホスト名。例: `game.example.com`
- `SECRET_KEY`: Flask の秘密鍵
- `FLASK_DEBUG`: 開発時は `1`、公開時は `0`

## ファイル構成
```
othello-game/
├── backend/
│   ├── app.py                 # エントリーポイント
│   ├── game_logic.py          # オセロロジック
│   ├── shogi_logic.py         # 将棋ロジック
│   ├── game_store.py          # ゲーム状態/AI設定ストア
│   ├── socket_utils.py        # Socketハンドラ共通ユーティリティ
│   ├── handlers/
│   │   ├── game_handlers.py   # create/join/reset
│   │   ├── move_handlers.py   # make_move
│   │   └── ai_handlers.py     # set_ai/get_ai_info
│   ├── templates/             # HTMLテンプレート
│   ├── static/                # JS/CSS/画像
│   ├── tests/                 # 最小ユニットテスト
│   └── requirements.txt       # Python依存関係
├── Dockerfile              # Dockerイメージ定義
├── docker-compose.yml      # Docker Compose設定
└── README.md               # このファイル
```

## カスタマイズ
- オセロロジックは `backend/game_logic.py` を編集
- 将棋ロジックは `backend/shogi_logic.py` を編集
- Socketイベント処理は `backend/handlers/` 配下を編集
- UIは `backend/templates/` と `backend/static/` を編集

## テスト実行

以下で標準ライブラリ `unittest` による最小テストを実行できます。

```bash
python3 -m unittest discover -s backend/tests
```

## 公開時の注意

- Socket.IO のクライアントは CDN ではなく、サーバー同梱の `/socket.io/socket.io.js` を使います。
- HTTPS 終端は Caddy に任せています。Nginx にしたい場合は `docker-compose.yml` と `Caddyfile` を差し替えてください。
- ゲーム状態とマッチング状態はメモリ内管理です。コンテナ再起動で消えます。

公開手順の詳細は以下を参照してください。

- `docs/gcp-vm-deploy.md`
- 環境変数テンプレート: `.env.example`

## 将棋AI: CPU向けMLモデル作成

将棋AIで `ML Policy (CPU)` / `onnx` エンジンを使うには、学習とONNX書き出しを1回実行してください。

詳細な手順、CLI引数の完全一覧、保存形式、トラブルシュートは以下を参照してください。

- `docs/shogi-ml-guide.md`

```bash
# プロジェクトルートで実行
cd backend
python3 -m ml.train_policy --games 30 --max-plies 80 --teacher-depth 2
python3 -m ml.export_onnx --weights models/shogi_policy_weights.npz --output models/shogi_policy.onnx
```

出力先:
- `backend/models/shogi_policy_weights.npz`
- `backend/models/shogi_policy_meta.json`
- `backend/models/shogi_policy.onnx`

モデルが未配置の場合、`ml` / `onnx` エンジンは安全に Minimax にフォールバックします。
