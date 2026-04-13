---
title: Health Endpoint Response Examples
status: active
draft_status: n/a
created_at: 2026-04-13
updated_at: 2026-04-13
references:
  - ../../reference/health_checker/architecture_and_commands.md
  - ./common_use_cases.md
  - ./discord_bot_operations.md
related_issues: []
related_prs: []
---

## Overview
- 本ガイドは、Simple Health Checker で監視しやすい HTTP ヘルスエンドポイントのレスポンス例をまとめる。
- 現状実装ではレスポンス本文を解析せず、HTTP ステータスコードとタイムアウト/例外だけで成否を判定する。

## Prerequisites
- 監視対象が HTTP/HTTPS で公開されている。
- `/monitor add` または `/monitor edit` で `expected_status_codes` を設定できる。
- 監視対象のアプリ側で、正常/異常に応じて HTTP ステータスコードを切り替えられる。

## Setup / Usage
### 推奨方針
- 正常時は `200 OK` を返す。
- 異常時は `503 Service Unavailable` など、`expected_status_codes` に含めないステータスを返す。
- 軽量なレスポンスを短時間で返し、DB や外部APIへの重い依存を増やしすぎない。
- `Cache-Control: no-store` を付け、キャッシュ経由で古い正常判定が見えないようにする。

### 最小構成の例
- ステータスコードだけで十分に監視できるため、最小構成なら空本文または短い JSON でよい。

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store

{"status":"ok"}
```

### 推奨レスポンス例
- 運用者が手動確認しやすいよう、本文には状態と最低限のメタデータを含めるとよい。
- ただし、本アプリの現状では本文の `status` 値は監視判定には使われない。

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store

{
  "status": "ok",
  "service": "my-discord-bot",
  "version": "1.4.2",
  "timestamp": "2026-04-13T04:40:00Z",
  "uptime_seconds": 86432
}
```

### 異常時レスポンス例
- 異常は本文ではなくステータスコードで表現する。
- 監視上は `503` を返すことが重要で、本文は補助情報として扱う。

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json; charset=utf-8
Cache-Control: no-store

{
  "status": "error",
  "service": "my-discord-bot",
  "timestamp": "2026-04-13T04:40:10Z",
  "reason": "discord gateway disconnected"
}
```

### monitor 設定例
- Discord Bot のヘルスエンドポイントを監視する場合は、`200` のみを正常扱いにする設定が扱いやすい。

```text
name: my-discord-bot
url: https://bot.example.net/healthz
method: GET
timeout_seconds: 5
expected_status_codes: 200
interval_seconds: 30
failure_threshold: 2
recovery_threshold: 2
```

## Best Practices
- `/healthz` は認証不要かつ高速に応答できる専用エンドポイントとして分離する。
- 本当に致命的な異常だけを `503` にし、一時的な補助機能の劣化まですべて失敗扱いにしない。
- `timestamp` や `version` を含め、手動確認時に「古いプロセスが返していないか」を見分けやすくする。
- 本文に詳細情報を含めてもよいが、機密情報や内部構成を過度に露出しない。
- 将来本文チェック機能を追加しても破綻しにくいよう、`status`, `service`, `timestamp` などのキーを安定させる。

## Troubleshooting
- 本文で `"status": "error"` を返しているのに通知されない:
  - 現状は本文を見ていないため、HTTP ステータスコードを `200` 以外に変更する。
- `unexpected status code` が出る:
  - 監視設定の `expected_status_codes` と実際のレスポンスコードを合わせる。
- ヘルスチェックで false positive が多い:
  - エンドポイント内の重い処理を減らし、`timeout_seconds` と `failure_threshold` を調整する。
- CDN やリバースプロキシ経由で古い結果が返る:
  - `Cache-Control: no-store` を追加し、必要に応じてキャッシュレイヤをバイパスする。

## References
- `README.md`
- `./common_use_cases.md`
- `./discord_bot_operations.md`
- `../../reference/health_checker/architecture_and_commands.md`
