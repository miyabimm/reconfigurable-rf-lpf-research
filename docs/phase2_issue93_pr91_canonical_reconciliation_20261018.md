# Issue #93 — PR #91を第1波監査の正本に採用する非破壊整理（2026-10-18）

> **所有者の今回の明示指示：PR #91を正本として整理開始。** これは正本選択と非破壊的な整理・照合の指示であり、個別workflowや研究原本の削除・停止・Git ref削除の承認ではない。本変更に含まれる退役・削除・無効化は0件。Phase 2継続、Phase 3未承認。

## 1. 判定基準・対象SHA

- 基準main：`d437b03ac495102f692de532d9bde62b809c1686`（[PR #91](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/91)統合後）。
- [Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)、[PR #92](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/92)は重複検査の相違・未承認退役を記録。
- **正本**：`.github/workflows/phase2_bc_wave1_consolidated.yml`（PR #91、変更前Git blob `ef3cb7cd00ef3c7a299ac2a627247765855fb6ad`）。
- **補助的な重複候補**：`.github/workflows/phase2_first_wave_retention_parity.yml`（PR #92、Git blob `12e14df94b18f5c6ce9c8a66528154095279214f`）。現在は保持。
- 個別5原本のGit blob：W2 `e0edee51a0684dad390482f97d661549a69ff623`、W3 `17ce8d94355c4fb326d9f927671864a56a3eb771`、EXP-042 crosswalk `c2cb776bba727b9fcc64f05a6ed255266ffd69f4`、EXP-042 six originals `d2ba86955cb6c5eb2bb9b043479e3bb997750bb7`、EXP-046/047 provenance `e06d4b890173fe46dd00564ec25a5d1733ab7dcb`。
- 判定行列：[8行のソース別対応表](../data/repository_reviews/phase2_issue93_pr91_canonical_parity_matrix_20261018.csv)。原本SHAは歴史固定の復元指標であり、本変更で差し替えない。

## 2. 確認済みの機能対応

| 原本 | PR #92（5個の独立job） | 正本PR #91（単一job内の手順） | 固定記録の照合 |
|---|---|---|---|
| `phase2_cleanup_w2.yml` | `w2-topology` | W2 unittest + build `--check` | 派生CSV・JSON・文書 |
| `phase2_cleanup_w3.yml` | `w3-source-restoration` | W3復元 + W1リンク | D-001～004の履歴／旧46原本 |
| `phase2_w4_exp042_crosswalk.yml` | `exp042-crosswalk` | W4 ZIP crosswalk + SHA/CRC | 元10 ZIP／19 member・CSV/JSON |
| `phase2_w4_exp042_missing_variants.yml` | `exp042-six-original-members` | 未選別6元JSONの復元確認 | 元run・variant・SHA |
| `phase2_w4_exp046_exp047_provenance.yml` | `exp046-exp047-provenance` | EXP-046/047出典監査 | 131元出典・訂正系列 |

PR #91だけが、`scripts/verify_phase2_bc_exp046_lossless.py --verify-committed`による**EXP-046の元3 batch JSONのバイト完全復元**を含む。元データは10配置×30成分、計424,233件の当時の報告評価であり、今回の最適化・独立MNA再実行件数ではない。[第1波記録](phase2_bc_wave1_consolidation_20261018.md)で原本3件と固定圧縮アーカイブ双方の保全を確認している。

実行履歴の区別：
- PR #91 HEADの[CI 39101884013](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39101884013)：SUCCESS。PR-head SHA `b0f62667b3256a6a25b064eaedd6ce77d1a437fb`。
- PR #92 HEADの[CI 39102284350](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39102284350)：5 jobともSUCCESSとIssue #93に記録。PR-head SHA `a663787f8f5bd35127eb86b66c9c4e4554eb5dfc`。
- 最新main `d437b03ac495...`の[Phase 2 regression 39102485318](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39102485318)：SUCCESS。
- **上記3 runは異なる目的・異なるSHAであり、2後継workflowが同一main SHAで独立にSUCCESSだったとの主張ではない。**
- **PR #94 第1回HEAD `c47c3355666d8eedde5c9827c9facd15a82087ba`で実際に同SHA実行済み**：[正本PR #91型CI run 39106177167](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39106177167) SUCCESS、[比較対象PR #92型CI run 39106177073](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39106177073) SUCCESS。W1/W3/W4/W5の該当監査CIもSUCCESS。ただし**この第1回HEADはmainへ未統合**であり、更新後のbranch HEAD／将来のmain SHAのSUCCESSを意味しない。

## 3. 今回の実装 — PR #91のtriggerを追加で保護

PR #92の広い`pull_request.paths`をPR #91正本に移すため、既存の個別パス列挙は残し、次の包含パターンだけを**追加**する。

```yaml
      - '.github/workflows/phase2_first_wave_retention_parity.yml'
      - 'scripts/**'
      - 'data/catalog/**'
      - 'data/repository_reviews/**'
      - 'data/pareto_snapshots/**'
      - 'experiments/chatgpt_topology_search/runs/EXP-042/**'
      - 'experiments/chatgpt_topology_search/runs/EXP-046/**'
      - 'experiments/chatgpt_topology_search/runs/EXP-047/**'
      - 'docs/**'
```

この**静的なpaths包含**はPR #92にあった8つの広域パターンと自身のworkflow変更パスをPR #91で受けるためのもの。PR #91の既存コマンド、`workflow_dispatch`、`permissions: contents: read`、成果物、旧workflow、RF制約、実験原本を変更しない。包含パターン拡大によりCI実行頻度は増え得るため、後続で費用・タイムアウトを監視する。

## 4. 同等でない運用インターフェースと保留ゲート

**5検査のコマンド被覆とworkflowの運用同等性は別物。** 以下は廃止可と証明したものではない。

1. **job/check名**：PR #92は5 job（`w2-topology`等）、PR #91は1 job（`five-original-checks-without-retirement`）。required checksや外部連携のcheck名依存を照合してから移行する。
2. **artifact**：PR #92はEXP-042 crosswalk・six originals・EXP-046/047出典の3個別artifact、PR #91は`phase2-bc-first-wave-parity-evidence`1件に統合、保持30日。名称・ディレクトリ構造を参照する消費者の有無は未確定。
3. **実験の初期発見用フラグ**：旧W4 workflowの`--emit-csv-chunks`、`--emit-original-chunks`等は正本の固定保存済み出典照合には含めていない。将来の再発見や旧手動dispatchの必要性を個別に確認。
4. **権限・保護設定**：mainのbranchメタデータは`protected: false`、リポジトリrulesets取得は`[]`。ただしbranch-protection詳細APIはコネクタ403で取得不可。組織規則／外部required-check消費者の不存在を証明したものではない。
5. **実行履歴・復元**：旧workflowの手動dispatch・元run artifact・履歴・ブランチ参照と、上記の固定Git blob SHAからの元定義復旧手順を退役前に確認する。
6. **main統合後の同SHA検証**：PR #91正本の拡張trigger、元10 ZIP/19 member、EXP-042元6 JSON、EXP-046/047 131原本、EXP-046元3 JSONバイト復元、W3/W1リンク、全回帰を同一revisionで確認する。コネクタからのジョブ確認やプルリクエストCI結果を、独立RF解析の代用にしない。

## 4a. 2026-10-18 main上の正本監査の追補結果

**本節はPR #94統合後の実行済み追補であり、上記PR-head当時の「未実施」記録を遡及改変しない。**

- [PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94) は main `69247eba09a8a82a8a9ce4db22a334e7e612e280` にマージ済み。[そのSHAのPhase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107016474) は**SUCCESS**。
- [PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95) は正本の自己変更時のみ`main` `push`で同じ検査を走らせる最小triggerを追加し、main `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d` にマージ済み。一般の`docs/**`等のmain pushでは追加監査を走らせない。
- **同一main SHAでの正本検査が実行済み**：[PR #95統合後の正本B/C audit run 39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329) は`push` / `head_sha=a8cf6ee98b06...` / `SUCCESS`。単一job `five-original-checks-without-retirement` SUCCESS、結合成果物 `phase2-bc-first-wave-parity-evidence`（31,770 bytes／期限付き）を確認。元5検査とEXP-046元3 JSON完全復元の固定出典検証ゲートを本main SHAで通過したという意味であり、独立RF数値再実行ではない。
- 同SHAの[Phase 2 regression run 39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399) はこの追補の作成時点で**実行中**。回帰全体の成否を正本CIから推測しない。
- **退役前の静的参照チェック**：main上の`docs/`以下Markdown 85件と`.github/workflows/` YAML 49件の文字列参照を確認。PR #92定義名・旧3 artifact名・新正本CI名は、正本／重複workflow定義と歴史・整理報告2文書にのみ明示参照があった。この限定チェックでは`scripts/`、`tests/`、APIの動的参照やGitHub外のrequired-check / artifact利用は確認できない。
- PR #92と旧5workflowの6件は、それぞれ保護対象Git blob SHAから取得した内容とmain現物が一致。Git blobからの**定義取得**は確認済みだが、退役後の手動dispatchや旧run再演の完全復旧まで保証していない。

**残ゲート**：個別job/check名と3 artifact名の下流消費者、外部設定・手動起動用途、branch protection API 403の解消、PR #92および旧5定義の個別所有者削除承認。原本・定義の削除停止0件を維持する。

## 5. 削除なしでの完了条件と次工程

- **今回の変更**：PR #91を正本とする判定を記録し、正本のPR trigger対象を追加し、対応行列をGitに作成。**削除／無効化／移動 0件、Git ref変更 0件**。
- **次ゲート**：ブランチCIとmain同SHA検証、required checks／artifact／手動dispatch／外部参照の照合。これらを済ませても自動的に退役しない。
- **別途明示承認が必要**：まずPR #92の`phase2_first_wave_retention_parity.yml`、次に5つの旧workflowについて**それぞれ**停止・削除の対象、元SHA、復元手順、退役後CIに欠落しないことを示す別PR。EXP-046元3 JSONも同様に**個別審査・個別承認まで残す**。
- **研究境界**：正式RF-F003／試験RF-T005を混合しない。最悪IL・H2/H3、連続帯域、独立MNA、Q(f)/SRF/EM/実測を本整理作業で再計算・保証しない。Phase 3を開始しない。
