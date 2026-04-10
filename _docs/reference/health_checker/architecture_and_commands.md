---
title: Health Checker Architecture Reference
status: active
draft_status: n/a
created_at: 2026-04-10
updated_at: 2026-04-10
references:
  - ../../guide/health_checker/discord_bot_operations.md
  - ../../guide/health_checker/common_use_cases.md
related_issues: []
related_prs: []
---

## Overview
- 監視ロジック、永続化、通知、Discord UI を分離した構成を採用する。
- 実データの正本は SQLite で、Discord は SQLite 操作用のフロントエンドとして動作する。

## API
### `MonitorService`
- **Summary**: 定期実行・状態遷移・通知トリガ・サマリー送信を管理する。
- **Parameters**:
  - `repository (MonitorRepository)` — 永続化層
  - `checker (HTTPChecker)` — HTTP 実行層
  - `poll_loop_seconds (int)` — スケジューラ周期
  - `max_parallel_checks (int)` — 並列実行数
  - `notifier (DiscordNotifier | None)` — Discord 通知層
- **Returns**: `run_single_check` は `(CheckResult, MonitorState)`
- **Errors**: ループ内例外は握りつぶさずログ出力し、プロセス継続
- **Examples**: `MonitorService.run_single_check(monitor)`

### `SQLiteMonitorRepository`
- **Summary**: SQLite への CRUD、状態管理、履歴管理を担当する。
- **Parameters**:
  - `db_path (Path)` — SQLite ファイル
- **Returns**: `Monitor`, `MonitorState`, `EventLog` など
- **Errors**: SQL 例外を上位へ伝播（呼び出し元でログ化）
- **Examples**: `initialize`, `close`, `create_monitor`, `list_due_monitors`

### Discord Slash Commands (`/monitor`, `/auth`)
- **Summary**: 監視対象の管理・参照と、管理権限ACLの操作を行う。
- **Parameters**:
  - `list`, `detail`, `history`, `check`
  - 管理制限あり: `add`, `edit`, `pause`, `resume`, `delete`, `summary_now`
  - ACL管理: `auth grant`, `auth revoke`（サーバー管理者のみ）, `auth list`
- **Returns**: エフェメラルメッセージ、必要に応じて button/select/modal UI
- **Errors**: 不正入力はメッセージで通知
- **Examples**: `/monitor add`, `/monitor detail monitor_id:1`

## Notes
- SQLite テーブル:
  - `monitors`: 監視対象定義
  - `monitor_state`: 現在状態と連続成功/失敗回数、最終通知関連情報
  - `event_logs`: チェック結果と状態遷移履歴
  - `admin_acl`: 管理操作を許可するユーザーACL
  - `admin_acl_audit`: ACL付与/削除の監査ログ
- SQLite 接続管理:
  - repository 内で共有接続を保持し、都度接続を避ける。
  - 書き込み経路は lock で逐次化し、`database is locked` リスクを抑制する。
  - 接続異常時は再接続し、PRAGMA を再適用する。
  - 終了時は `close()` を呼び出して接続を明示クローズする。
- DOWN 通知時のみロール/ユーザーメンションを送る。
- 監視対象のコア処理は Discord 依存コードから分離されている。
