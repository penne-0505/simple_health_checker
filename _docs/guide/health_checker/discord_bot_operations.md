---
title: Discord Bot Operations Guide
status: active
draft_status: n/a
created_at: 2026-04-10
updated_at: 2026-04-13
references:
  - ../../reference/health_checker/architecture_and_commands.md
  - ./common_use_cases.md
  - ./health_endpoint_response_examples.md
related_issues: []
related_prs: []
---

## Overview
- Discord bot ベースの監視システムを Fedora Linux 上で継続運用するための手順をまとめる。
- 監視対象の登録・更新・停止・履歴確認を Discord UI から実施する。

## Prerequisites
- Python 3.11 以上
- `uv`
- Discord Bot Token
- 監視通知先チャンネル
- `.env` の設定

## Setup / Usage
- 起動: `uv run python -m simple_health_checker.app`
- 登録: `/monitor add`
- 編集: `/monitor edit`
- 停止/再開: `/monitor pause`, `/monitor resume`
- 手動チェック: `/monitor check`
- 状態確認: `/monitor list`, `/monitor detail`, `/monitor history`
- ACL 管理: `/auth grant`, `/auth revoke`, `/auth list`

## Best Practices
- `failure_threshold` を 2 以上に設定し、単発障害で DOWN 判定しない。
- `recovery_threshold` を 2 以上にして瞬間復旧での誤通知を抑制する。
- サーバー管理者が `/auth grant` で ACL 管理者を付与し、日常運用を委譲する。
- 定時監視の俯瞰のため `SUMMARY_CHANNEL_ID` を設定する。
- 長期運用では SQLite の lock/reconnect ログを定期確認する（`journalctl` 推奨）。
- Discord Bot 側の `/healthz` は、正常時 `200`・異常時 `503` を返す専用エンドポイントとして設計する。

## Troubleshooting
- slash command が出ない: `COMMAND_GUILD_ID` を設定してギルド同期を確認する。
- 通知が飛ばない: チャンネルIDの設定と bot の送信権限を確認する。
- DOWN/UP 遷移しない: `failure_threshold` / `recovery_threshold` が高すぎないか確認する。
- 起動失敗: `DISCORD_BOT_TOKEN` と `SQLITE_PATH` の設定、依存インストール状況を確認する。
- `database is locked` が出る: 一時的な負荷集中の可能性があるため、`MAX_PARALLEL_CHECKS` を下げ、継続する場合はイベントログ量を見直す。

## References
- `README.md`
- `./common_use_cases.md`
- `./health_endpoint_response_examples.md`
- `../../reference/health_checker/architecture_and_commands.md`
- `deploy/systemd/simple-health-checker.service`
