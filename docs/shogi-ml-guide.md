# 将棋MLモデル完全ガイド

このドキュメントは、このリポジトリで使っている将棋MLモデルの学習、保存、ONNX変換、推論利用までを完全に説明します。

対象コード:
- `backend/ml/train_policy.py`
- `backend/ml/export_onnx.py`
- `backend/shogi_ai.py`
- `backend/shogi_ml_features.py`

## 1. 全体フロー

1. 既存AI(Minimax)を教師として自己対局データを作る
2. ロジスティック回帰で重みを学習する
3. 学習重みを `.npz` で保存する
4. `.npz` を ONNX へ変換する
5. 対局時に `ml` または `onnx` エンジンで ONNX 推論を使う
6. モデル未配置時は Minimax にフォールバックする

## 2. 前提環境

- Python 3.9+
- 依存パッケージ ( `backend/requirements.txt` )
  - Flask
  - Flask-SocketIO
  - eventlet
  - numpy
  - onnx
  - onnxruntime

インストール例:

```bash
cd backend
pip install -r requirements.txt
```

## 3. 学習と保存の基本実行

## 3.1 backend ディレクトリで実行する場合 (推奨)

```bash
cd backend
python3 -m ml.train_policy \
  --games 30 \
  --max-plies 80 \
  --teacher-depth 2 \
  --epochs 14 \
  --learning-rate 0.08 \
  --l2 1e-4 \
  --seed 7 \
  --output models/shogi_policy_weights.npz \
  --meta models/shogi_policy_meta.json

python3 -m ml.export_onnx \
  --weights models/shogi_policy_weights.npz \
  --output models/shogi_policy.onnx
```

この実行で生成されるファイル:
- `backend/models/shogi_policy_weights.npz`
- `backend/models/shogi_policy_meta.json`
- `backend/models/shogi_policy.onnx`

## 3.2 プロジェクトルートで実行する場合

```bash
python3 -m backend.ml.train_policy \
  --games 30 \
  --max-plies 80 \
  --teacher-depth 2 \
  --output backend/models/shogi_policy_weights.npz \
  --meta backend/models/shogi_policy_meta.json

python3 -m backend.ml.export_onnx \
  --weights backend/models/shogi_policy_weights.npz \
  --output backend/models/shogi_policy.onnx
```

注意:
- 相対パスはカレントディレクトリ基準です。
- `cd backend` しているのに `--output backend/models/...` を指定すると `backend/backend/models/...` に保存されます。

## 4. CLI引数完全一覧

## 4.1 train_policy.py

コマンド:

```bash
python3 -m ml.train_policy [options]
```

引数:

| 引数 | 型 | 既定値 | 制約/補正 | 説明 |
|---|---|---|---|---|
| `--games` | int | `30` | `max(1, value)` | 学習データ生成に使う自己対局数 |
| `--max-plies` | int | `80` | `max(8, value)` | 1局あたり最大手数 |
| `--teacher-depth` | int | `2` | `min(max(value,1),4)` | 教師 Minimax の探索深さ |
| `--epochs` | int | `14` | `max(1, value)` | 学習反復回数 |
| `--learning-rate` | float | `0.08` | `max(1e-4, value)` | 学習率 |
| `--l2` | float | `1e-4` | `max(0.0, value)` | L2正則化係数 |
| `--seed` | int | `7` | なし | 乱数シード |
| `--output` | str | `backend/models/shogi_policy_weights.npz` | なし | 学習重み(npz)の保存先 |
| `--meta` | str | `backend/models/shogi_policy_meta.json` | なし | 学習メタ情報(json)の保存先 |

保存物仕様:
- `weights` (float32 ベクトル)
- `bias` (float32 スカラー)
- `feature_dim` (int32)

メタ情報仕様:
- `training`
  - `games`, `max_plies`, `teacher_depth`, `learning_rate`, `epochs`, `l2`, `seed`
- `dataset`
  - `samples`: 生成サンプル数
  - `feature_dim`: 特徴量次元
  - `positive_ratio`: 正例比率

実装上の重要点:
- 教師手は `select_shogi_move(..., {"engine": "minimax" ...})` で生成
- 盤面ごとの全合法手を特徴量化し、教師手だけ正例(1.0)、それ以外を負例(0.0)
- クラス不均衡を考慮して正例重み `pos_weight = neg_count / pos_count`

## 4.2 export_onnx.py

コマンド:

```bash
python3 -m ml.export_onnx [options]
```

引数:

| 引数 | 型 | 既定値 | 制約 | 説明 |
|---|---|---|---|---|
| `--weights` | str | `backend/models/shogi_policy_weights.npz` | ファイル存在必須 | 入力する学習重み(npz) |
| `--output` | str | `backend/models/shogi_policy.onnx` | なし | 出力する ONNX モデル |

ONNXモデル仕様:
- 入力名: `features`
- 入力形状: `[None, feature_dim]`
- 出力名: `scores`
- 出力形状: `[None, 1]`
- 演算: `MatMul` + `Add` (線形モデル)
- opset: 13

## 5. 推論時の利用方法

将棋AI設定で以下のどちらかを選ぶと ONNX 推論パスに入ります。
- `engine = ml`
- `engine = onnx`

読み込み先:
- 既定: `backend/models/shogi_policy.onnx`
- 上書き: AI設定に `model_path` を渡すとそのファイルを使用

実装仕様:
- `backend/shogi_ai.py` の `MLShogiAI` が合法手を列挙
- 各合法手を `extract_move_features` で特徴量化
- ONNX推論のスコア順で手を選択
- 難易度ごとの選択:
  - easy: 上位6手からランダム
  - medium: 上位3手からランダム
  - hard: 最善手1択

フォールバック条件:
- ONNXファイルがない
- onnxruntime が使えない
- 特徴量次元が不一致
- 出力サイズが合法手数と一致しない
- 推論中例外が発生

上記いずれでも Minimax に自動フォールバックします。

## 6. 推奨パラメータ

初回動作確認:
- `--games 5 --max-plies 40 --teacher-depth 1 --epochs 5`

実運用の初期値:
- `--games 30 --max-plies 80 --teacher-depth 2 --epochs 14`

精度寄り:
- `--games 80 --max-plies 120 --teacher-depth 3 --epochs 20`

注意:
- `teacher-depth` を上げるとデータ生成時間が大きく増加
- `games` と `max-plies` を同時に上げるとサンプル数が急増

## 7. 再学習とモデル更新手順

1. 既存成果物をバックアップ
2. 新しいパラメータで `train_policy` を実行
3. `export_onnx` を実行
4. 出力ファイルを `backend/models/shogi_policy.onnx` に配置
5. サーバー再起動後に `ml` エンジンで対局確認

バックアップ例:

```bash
cd backend/models
cp shogi_policy_weights.npz shogi_policy_weights.npz.bak
cp shogi_policy_meta.json shogi_policy_meta.json.bak
cp shogi_policy.onnx shogi_policy.onnx.bak
```

## 8. 検証チェックリスト

```bash
cd backend
python3 -m ml.train_policy --games 1 --max-plies 8 --teacher-depth 1 --epochs 2 \
  --output models/shogi_policy_weights.npz --meta models/shogi_policy_meta.json
python3 -m ml.export_onnx --weights models/shogi_policy_weights.npz --output models/shogi_policy.onnx
python3 -m unittest tests.test_shogi_ai tests.test_shogi_logic
```

確認ポイント:
- 3つの成果物が生成される
- テストが通る
- 将棋画面で `ML Policy (CPU)` を選択して進行する

## 9. トラブルシュート

1. `ModuleNotFoundError: No module named ml`
- 原因: 実行ディレクトリ不一致
- 対処: `cd backend` して `python3 -m ml.train_policy` を使う

2. `dataset is empty; increase games/max_plies`
- 原因: データ生成が足りない
- 対処: `--games` と `--max-plies` を増やす

3. ONNXモデルが読み込まれず Minimax になる
- 原因: モデル未配置、パス違い、onnxruntime未導入など
- 対処:
  - `backend/models/shogi_policy.onnx` が存在するか確認
  - `pip install -r backend/requirements.txt` を再実行
  - 必要なら AI設定で `model_path` を明示

4. 出力先が想定と違う
- 原因: 相対パスとカレントディレクトリの組み合わせ
- 対処: `--output` / `--meta` / `--weights` / `--output` を常に明示

## 10. 変更時のメモ

- 特徴量次元を変えた場合は、必ず再学習して `.npz` と `.onnx` を作り直す
- 旧モデルと新コードで `feature_dim` が不一致だとフォールバックする
- 本モデルは軽量線形モデルのため高速だが、棋力は教師データ品質に依存する
