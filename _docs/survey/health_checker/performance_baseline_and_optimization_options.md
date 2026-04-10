---
title: Health Checker Performance Baseline and Optimization Options
status: active
draft_status: n/a
created_at: 2026-04-10
updated_at: 2026-04-10
references:
  - ../../reference/health_checker/architecture_and_commands.md
related_issues: []
related_prs: []
---

## Background
- 本プロジェクトは非常に非力なマシンでの常駐運用を前提としている。
- 監視対象の増加や通知頻度の上昇に伴って、CPU/IO負荷のボトルネックが顕在化する可能性がある。
- 実装修正前に、現状挙動をテストで固定しつつ、最適化候補とリスクを整理する必要がある。

## Objective
- 現行実装のパフォーマンス上の問題点を特定する。
- 低リスクで効果の高い改善候補を優先順で列挙する。
- 各改善候補について、挙動変化リスクを明文化する。

## Method
- 対象モジュールを静的レビューした。
  - `monitoring/service.py`
  - `repository/sqlite.py`
  - `monitoring/http_checker.py`
- 実行パス上のI/O回数、DBクエリ数、接続回数、状態更新回数を確認した。
- 監視ループ、状態遷移、通知、サマリー集計の各フローでボトルネック候補を抽出した。

## Results
- 実装済み改善:
  - `run_single_check` の `upsert_state` 二重実行を解消し、1回保存へ統一。
  - due 判定で取得した `state` をそのままチェック処理で再利用。
  - `list_due_monitors` とサマリー生成の state 取得を JOIN 一括化。
  - `SQLiteMonitorRepository` を共有接続化し、`close()` による明示クローズを導入。
  - 書き込み経路に `asyncio.Lock` を導入し commit を逐次化。
  - 接続断等に対して最小限の再接続処理（PRAGMA再適用込み）を導入。
- 軽量ベンチ結果（`list_due_monitors` 実行時間）:
  - monitor 10件: warm avg/p95 = `0.146ms / 0.224ms`
  - monitor 50件: warm avg/p95 = `0.384ms / 0.501ms`
  - monitor 100件: warm avg/p95 = `0.688ms / 0.924ms`
  - 参考（強制再接続時）:
    - 10件: `0.552ms / 0.649ms`
    - 50件: `0.792ms / 0.897ms`
    - 100件: `1.091ms / 1.364ms`
- 既存の良い点:
  - `aiohttp.ClientSession` は使い回している。
  - `Semaphore` による同時実行制御がある。
  - 監視ループが busy wait になっていない。

## Discussion
- 効果:
  - 監視ループの DB アクセス回数削減により、非力マシンでも監視対象増加への耐性が改善。
  - 共有接続化により接続開閉オーバーヘッドを縮小。
- 残リスク:
  - 長寿命接続のため、異常時の再接続分岐は継続監視（ログ観察）が必要。
  - 書き込みロック導入により高負荷時は待ち時間が伸びる可能性がある。
  - テストで `Event loop is closed` 警告が一度発生したため、テスト側で `repo.close()` を確実化して解消した。

## Recommended Actions
- 定常運用で `database is locked` / reconnect 系ログの有無を監視する。
- monitor 件数を増やしたときに、`POLL_LOOP_SECONDS` と `MAX_PARALLEL_CHECKS` を再調整する。
- 今後の性能改善候補として、必要であればイベントログの保持ポリシー（件数・期間）を追加する。
