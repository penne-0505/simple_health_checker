---
title: Common Health Check Use Cases
status: active
draft_status: n/a
created_at: 2026-04-10
updated_at: 2026-04-13
references:
  - ../../reference/health_checker/architecture_and_commands.md
  - ./discord_bot_operations.md
  - ./health_endpoint_response_examples.md
related_issues: []
related_prs: []
---

## Overview
- 本ガイドは、よくある2つの監視パターン（通常Webサイト / Discord Bot）で推奨設定を示す。
- 監視対象の登録は `/monitor add`、調整は `/monitor edit` を前提とする。

## Prerequisites
- Bot が起動済み（`uv run python -m simple_health_checker.app`）。
- 管理操作可能なユーザー（サーバー管理者または ACL 登録済み）。
- 通知チャンネルが作成済み。

## Setup / Usage
### Use Case 1: 通常のWebサイト監視
- **想定対象**: 企業サイト、ランディングページ、API Gateway ヘルスページ
- **推奨設定例**:
  - `name`: `corp-website`
  - `url`: `https://example.com/`
  - `method`: `GET`
  - `timeout_seconds`: `10`
  - `expected_status_codes`: `200,301,302`
  - `interval_seconds`: `60`
  - `failure_threshold`: `3`
  - `recovery_threshold`: `2`
  - `notification_channel_id`: 監視通知チャンネル
  - `alert_channel_id`: 同一または専用アラートチャンネル
  - `mention_role_id`: 障害対応ロール
  - `enabled`: `true`
- **運用ポイント**:
  - CDN やリダイレクトがあるサイトは `301/302` を許可する。
  - 一時的なネットワーク揺れ対策で `failure_threshold >= 2` を維持する。

### Use Case 2: Discord Bot 監視
- **想定対象**: 自作Discord Botのヘルスエンドポイント
- **推奨前提**:
  - Bot 本体に HTTP ヘルスエンドポイント（例: `/healthz`）を公開しておく。
  - `200` 返却時のみ正常扱いにする。
  - 本文は補助情報として JSON を返してよいが、正常/異常の判定は HTTP ステータスコードで表現する。
- **推奨設定例**:
  - `name`: `my-discord-bot`
  - `url`: `https://bot.example.net/healthz`
  - `method`: `GET`
  - `timeout_seconds`: `5`
  - `expected_status_codes`: `200`
  - `interval_seconds`: `30`
  - `failure_threshold`: `2`
  - `recovery_threshold`: `2`
  - `notification_channel_id`: bot運用通知チャンネル
  - `alert_channel_id`: 障害専用チャンネル（推奨）
  - `mention_user_id`: オンコール担当者
  - `enabled`: `true`
- **運用ポイント**:
  - 非力マシンでは監視間隔を短くしすぎない（まず `30s` から）。
  - false positive が多い場合は `timeout_seconds` と `failure_threshold` を先に調整する。
  - レスポンス例や推奨フィールドは `./health_endpoint_response_examples.md` を参照する。

## Best Practices
- 本番導入前に `/monitor check` で手動実行し、通知メッセージとメンション先を確認する。
- `/monitor history` で直近結果を確認し、しきい値を実測ベースで調整する。
- アラートチャンネルは通常通知と分離すると、障害時の見落としが減る。
- `SUMMARY_CHANNEL_ID` を設定し、全体状況を定時把握する。

## Troubleshooting
- `unexpected status code` が多い:
  - `expected_status_codes` を実際の挙動に合わせる（Webは 301/302 を許可検討）。
- タイムアウトが多い:
  - `timeout_seconds` を引き上げ、`interval_seconds` も合わせて調整する。
- DOWN/RECOVERED が頻繁に揺れる:
  - `failure_threshold` と `recovery_threshold` を上げる。
- 通知が来ない:
  - `notification_channel_id` と Bot 権限（送信/閲覧）を再確認する。

## References
- `README.md`
- `./discord_bot_operations.md`
- `./health_endpoint_response_examples.md`
- `../../reference/health_checker/architecture_and_commands.md`
