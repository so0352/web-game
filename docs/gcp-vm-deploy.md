# GCP VM で Docker 公開する手順

このドキュメントは、このリポジトリを GCP Compute Engine の VM 上で Docker Compose 起動し、Caddy で HTTPS 公開するための実行手順です。

対象構成:
- アプリ: Flask + Socket.IO (`othello` サービス)
- リバースプロキシ/HTTPS: Caddy (`caddy` サービス)

関連ファイル:
- `docker-compose.yml`
- `Caddyfile`
- `Dockerfile`
- `backend/app.py`

## 1. 事前準備

- GCP プロジェクト作成済み
- 独自ドメインを保有している
- ドメインの DNS レコードを編集できる
- VM の 80/443 を外部開放できる

## 2. GCP 側の作業

1. Compute Engine で VM を作成する

- OS 例: Ubuntu 22.04 LTS
- マシンタイプ目安: `e2-small` 以上
- 外部 IP は静的 IP 推奨
- ネットワークタグ例: `game-web`

2. ファイアウォールルールを作成する

```bash
gcloud compute firewall-rules create allow-http-https-game \
  --allow tcp:80,tcp:443 \
  --target-tags game-web

gcloud compute firewall-rules create allow-ssh-game \
  --allow tcp:22 \
  --target-tags game-web
```

3. DNS の A レコードを作成する

- 例: `othello.example.com` -> VM の静的外部 IP

確認:

```bash
dig +short othello.example.com
```

## 3. VM に Docker を導入

Ubuntu の例:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

その後、再ログインして反映。

## 4. アプリ配置と環境変数

1. リポジトリを配置

```bash
git clone <YOUR_REPOSITORY_URL>
cd othello-game
```

2. `.env` を作成

テンプレートを使う場合:

```bash
cp .env.example .env
```

```env
PUBLIC_DOMAIN=othello.example.com
SECRET_KEY=ここに十分長いランダム文字列
```

`SECRET_KEY` 生成例:

```bash
openssl rand -hex 32
```

補足:
- `PUBLIC_DOMAIN` は `Caddyfile` と `docker-compose.yml` で使用
- `SOCKETIO_CORS_ALLOWED_ORIGINS` は `https://${PUBLIC_DOMAIN}` が渡される

## 5. 起動

```bash
docker compose up -d --build
```

状態確認:

```bash
docker compose ps
docker compose logs -f caddy
docker compose logs -f othello
```

## 6. 公開確認

1. ブラウザで `https://<PUBLIC_DOMAIN>` にアクセス
2. トップ画面表示を確認
3. オセロ/将棋画面へ遷移できることを確認
4. 対局操作で Socket.IO 通信が成立することを確認

## 7. 更新運用

```bash
git pull
docker compose up -d --build
```

任意で不要イメージ削除:

```bash
docker image prune -f
```

## 8. トラブルシュート

1. 証明書が取れない

- `PUBLIC_DOMAIN` が正しいか
- DNS が VM 外部 IP を向いているか
- 80/443 が GCP ファイアウォールで開いているか

2. 画面は開くが Socket 接続失敗

- `SOCKETIO_CORS_ALLOWED_ORIGINS` の実値を確認
- 実際のアクセス URL が `https://<PUBLIC_DOMAIN>` と一致しているか確認

確認コマンド:

```bash
docker compose exec othello env | grep -E "PUBLIC_DOMAIN|SOCKETIO_CORS_ALLOWED_ORIGINS|SECRET_KEY"
```

3. 再起動時に証明書が毎回取り直しになる

- `caddy_data` / `caddy_config` ボリュームを削除していないか確認

## 9. デプロイチェックリスト

- [ ] VM に静的外部 IP を設定した
- [ ] 80/443 を開放した
- [ ] ドメインの A レコードを VM IP に向けた
- [ ] `.env` に `PUBLIC_DOMAIN` を設定した
- [ ] `.env` に本番用 `SECRET_KEY` を設定した
- [ ] `docker compose up -d --build` を実行した
- [ ] Caddy の証明書取得成功をログで確認した
- [ ] HTTPS でアクセス確認した
- [ ] 対局操作で Socket.IO 接続を確認した
