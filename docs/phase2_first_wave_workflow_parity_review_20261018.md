# Phase 2 リポジトリ整理：第1波5 workflowの非破壊移管検証（2026-10-18）

> 状態：**後継候補をPR上に追加、CI実行結果・機能同等性の最終判定は別ゲート**。研究原本・旧workflowは全件保持。削除・停止・Git ref変更・新規RF数値計算なし。Phase 2継続／Phase 3未承認。

## 出典・作業境界

- 調査起点main：`c83952a74c63c204265daf225edd252dc62d14e7`（PR #90統合後）。正式RF-F003、試験RF-T005の区分を変更しない。
- 方針正本：[C寄りのB保管・退役方針](phase2_Bc_retention_and_retirement_policy_20261018.md)。
- 新規の一時的な後継候補：[`phase2_first_wave_retention_parity.yml`（PR #92時点の歴史的ソース）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/552aa86775aaa2f7364ee441735afe6e07bc71b8/.github/workflows/phase2_first_wave_retention_parity.yml)。
- 5つの既存定義はそのまま維持し、同じ読み取り専用Python検証器を別jobで実行する。元のworkflow実行履歴・元run・SHAを上書きしない。
- 元データと候補台帳の再計算は行わない。これらの検査は**過去の原本・記録間の整合監査**であり、RF独立MNAやQ(f)、SRF、EMの検証ではない。

## 元workflowと後継jobの対応

| 元workflow（main Git blob SHA-1） | 後継job | 必須検証 | 対応状態 |
|---|---|---|---|
| `phase2_cleanup_w2.yml` (`e0edee51a0684dad390482f97d661549a69ff623`) | `w2-topology` | `tests.test_phase2_topology_search` + `build_phase2_topology_search.py --check` | 実装済み・PR CI待ち |
| `phase2_cleanup_w3.yml` (`17ce8d94355c4fb326d9f927671864a56a3eb771`) | `w3-source-restoration` | W3承認済み4件、Git履歴復元、D-005～007・旧46原本、W1リンク | 実装済み・PR CI待ち |
| `phase2_w4_exp042_crosswalk.yml` (`c2cb776bba727b9fcc64f05a6ed255266ffd69f4`) | `exp042-crosswalk` | 元ZIP→checkpoint CSVのバイト一致、JSON完全一致、10 ZIP／19 member・SHA／CRC、W1リンク | 実装済み・PR CI待ち |
| `phase2_w4_exp042_missing_variants.yml` (`d2ba86955cb6c5eb2bb9b043479e3bb997750bb7`) | `exp042-six-original-members` | 未選別3変種の元6 JSONの完全バイト復元・固定報告照合、10 ZIP SHA／CRC、W1リンク | 実装済み・PR CI待ち |
| `phase2_w4_exp046_exp047_provenance.yml` (`e06d4b890173fe46dd00564ec25a5d1733ab7dcb`) | `exp046-exp047-provenance` | EXP-046/047 131原本SHA・訂正系列、正式RF-F003とRF-T005の分離、保存CSVとJSONを照合、W1リンク | 実装済み・PR CI待ち |

## 既存監査と移管候補の相違

- 旧W4 crosswalk／EXP-046・047は、固定CSVがまだ無い初期発見段階を許容する条件分岐を持つ。新jobは**固定CSV・固定JSONの存在と一致を必須**とし、現在の保全済みスナップショットを対象とする。
- W4の`--emit-csv-chunks`／`--emit-original-chunks`は、以前の原本保全用CIログを生成する補助機能。新jobでは**再出力しない**。保存済み原本と対応記録の検証は実行する。ログの完全互換を要求する用途は元workflowを残す。
- 新workflowは複数jobを1定義に配置するため、Actionsのworkflow名、手動起動画面、job ID、run ID、artifact名、トリガーpath集合は旧5件と一致しない。job内の検証コマンド対応だけで**運用上の完全同等性を証明しない**。
- 旧5件は`workflow_dispatch`可能。新候補にも`workflow_dispatch`を設けるが、GitHub required checks・他workflowのjob名参照・通知・外部依存・実際の手動起動は別途確認する。
- 検証用後継workflowを追加するため、**移管中はworkflow定義数が一時的に増える**。これは削減実績ではない。

## 次回の完了判定ゲート（未実施・未承認）

1. このPRの5 jobを同一SHA上で完走し、各jobのSUCCESSと出力・元snapshot一致を保存する。現行mainの基準回帰も別途確認する。
2. 旧5 workflowの元CI結果と、新jobのチェック範囲・失敗モード・artifact・ログの差分を個別に精査する。単なるgrep・静的機能表だけで機能同等と判定しない。
3. 旧workflowを要求するbranch protection、required checks、手動再実行、外部ブランチ参照、復元に必要な元Git SHAを確認する。
4. 5件それぞれに対し、継続保全・移管完了・退役審査の独立した処置を記録する。**退役可と確定するまでは旧5件は保持**。
5. 後日、元path単位で所有者の明示承認を取得した場合に限り、別PRで停止または削除を扱う。承認が無ければ移管CIを追加しても削除しない。

## 原本保全と研究への影響

旧47 workflow、W4で重点確認した225原本、EXP-042の10 ZIP・19 member、EXP-046/047の131原本と訂正履歴を保持。元EXP-046の3 batch JSONに記録された10配置／30要素ベクトルは別の集約調査対象であり、この作業では統合・編集・削除しない。

**実装済みの作業と未実行の検証を区別する。** この文書を追加するだけで5件の代替CIが成功したと扱わない。最新結果は対象PRのChecksとActions実行履歴を参照する。
