# Simple Health Checker (Discord Bot)

Fedora Linux 上で常駐させることを想定した、Discord bot ベースの小規模監視システムです。  
HTTP/HTTPS エンドポイントを定期チェックし、状態遷移時のみ Discord に通知します。

## 機能

- 単一の Discord bot で通知と管理を統合
- 監視コアと Discord UI を分離した構成
- SQLite を正本とした永続化
- 複数監視対象を登録可能
- 閾値ベースの状態遷移（単発失敗で即 DOWN にならない）
- 状態変化時のみ通知（DOWN / RECOVERED）
- DOWN 時のみメンション
- 定時サマリー通知
- slash command / button / select menu / modal による管理

## ディレクトリ構成

```text
src/simple_health_checker/
  app.py                    # エントリポイント
  config.py                 # .env 設定ロード
  models.py                 # ドメインモデル
  repository/
    base.py                 # Repository 抽象
    sqlite.py               # SQLite 実装
  monitoring/
    http_checker.py         # HTTP チェック実行
    service.py              # スケジューラ/状態遷移/サマリー
  notification/
    discord_notifier.py     # Discord 通知
  discord_ui/
    bot.py                  # Slash command / UI コンポーネント

deploy/systemd/simple-health-checker.service
```

## セットアップ

1. Python 3.11+ と `uv` を用意
2. 仮想環境作成と依存インストール

```bash
uv sync
```

3. `.env.example` を `.env` にコピーして値を設定

```bash
cp .env.example .env
```

4. 起動

```bash
uv run python -m simple_health_checker.app
```

## 環境変数

最低限 `DISCORD_BOT_TOKEN` が必要です。主な設定は以下です。

- `SQLITE_PATH`: SQLite ファイルパス
- `POLL_LOOP_SECONDS`: ポーリング周期
- `MAX_PARALLEL_CHECKS`: 並列チェック数
- `SUMMARY_CHANNEL_ID`: サマリー通知先チャンネル ID
- `SUMMARY_INTERVAL_SECONDS`: サマリー送信間隔

## Slash Commands

- `/monitor list` 監視対象一覧 + select menu
- `/monitor detail` 詳細表示 + button 操作
- `/monitor add` 追加（modal 使用）
- `/monitor edit` 編集（modal 使用）
- `/monitor pause` 停止
- `/monitor resume` 再開
- `/monitor delete` 削除
- `/monitor check` 手動チェック
- `/monitor history` 直近履歴表示
- `/monitor summary_now` サマリー即時送信

管理権限が必要な操作（追加・編集・削除・停止・再開・summary_now）は、
「サーバー管理者」または `ACL` 登録ユーザーに制限されます。

### 管理権限 (ACL) コマンド

- `/auth grant user:<member>` 管理操作権限を付与（サーバー管理者のみ）
- `/auth revoke user:<member>` 管理操作権限を削除（サーバー管理者のみ）
- `/auth list` ACL 一覧表示（管理操作権限ユーザーのみ）

> 安全策として、最後の ACL 管理者は削除できません。

## 監視状態と通知仕様

- `failure_threshold` 到達で `DOWN`
- `recovery_threshold` 到達で `UP`（DOWN からの復帰時は RECOVERED として通知）
- 状態変化時のみ通知
- DOWN 通知のみメンション送信
- RECOVERED 通知は状態復帰時に 1 回のみ

## systemd サービス化 (Fedora)

`deploy/systemd/simple-health-checker.service` を必要に応じて編集して配置します。

```bash
sudo cp deploy/systemd/simple-health-checker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now simple-health-checker.service
sudo systemctl status simple-health-checker.service
```

`git pull`後など、コードを更新した際はサービスの再起動が必要です。

```bash
sudo systemctl restart simple-health-checker.service
```

## ログ

標準出力へ出力されるため、systemd では `journalctl` で確認できます。

```bash
journalctl -u simple-health-checker.service -f
```
