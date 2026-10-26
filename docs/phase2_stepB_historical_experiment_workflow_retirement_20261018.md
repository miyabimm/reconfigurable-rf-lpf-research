# Step B 第2弾：歴史実験workflow 28件の退役候補と復元（2026-10-18）

> **2026-10-18ユーザー明示承認済み：PR #102の28 YAML一括退役・削除。** この記録はPR #102のmain統合前に更新したものであり、統合を確認するまではmainで退役済みとは扱わない。基準mainは **31 workflow**、統合後の目標は**3 workflow**。RF数値結果・実験一次記録・テスト・Python・Git refsは変更しない。研究Phase 2継続／Phase 3未承認。

## 必要な最小限の再現経路

元の定義とコマンドは、[第1弾PR #101統合直後のmainコミット](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/commit/c6c23bab59aeeea70555b016bdec7806f72d239c)に固定保存されている。新しいcheckoutから参照する例：

```bash
git show c6c23bab59aeeea70555b016bdec7806f72d239c:.github/workflows/exp043_3l.yml
git show c6c23bab59aeeea70555b016bdec7806f72d239c:.github/workflows/lpf-p4-a.yml
git show c6c23bab59aeeea70555b016bdec7806f72d239c:.github/workflows/lpf-exp013.yml
```

**必要なときにだけ**当時のソースcommitへcheckoutし、`uv sync --frozen`後に元YAMLの具体的なPythonコマンド・matrix variant・seed・入力条件を読む。作業ディレクトリは分離し、実験原本を上書きしない。保存済み最終候補を**再評価するだけ**の場合は元探索workflowを実行する必要はなく、各EXPの`verify*.py`、`results`、`data/pareto_snapshots/`、`data/constraints/`、固定S2Pを使う。実行するまでは未実行と扱う。

元Git blob SHAは元ファイルの同一性照合用。**Gitの履歴は書き換えない**。以下は全28件の固有入口と復元元一覧。各行は元YAMLの内容を読んだ上での**再現の入口**であり、現在のmainでの実行成功を保証しない。

| 歴史的workflow（固定ソースへのリンク） | 元Git blob SHA | 実行入口・役割 |
|---|---|---|
| [`exp042-rf-t005-verify.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042-rf-t005-verify.yml) | `b97e4c440583c53f5aed0928b537c041cbdee167` | EXP-042 verify_rf_t005.py（固定S2Pと独立MNA） |
| [`exp042_area.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_area.yml) | `d140bac6d1fd6983ccf945fe975b6509d82f61fc` | EXP-042 optimize_area.py＋verify_area.py（3 variant） |
| [`exp042_manifest.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_manifest.yml) | `7a34365e898365d115f3c3c1b804c8a529049333` | scripts/bootstrap_exp042_manifest.py（旧研究ブランチへのpush） |
| [`exp042_passband_q.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_passband_q.yml) | `fcb85b8b52603202a9d71e79bc96c05db7217e68` | EXP-042 analyze_passband_q.py |
| [`exp042_pcb.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_pcb.yml) | `916f5e719f6582f86f51445cec5913088fbfec73` | EXP-042 optimize_pcb.py＋verify_area.py |
| [`exp042_rf_t005.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_rf_t005.yml) | `671422f8e2fa83d7e3fdab8b9f6ec5bb501437c9` | EXP-042 optimize.py＋verify.py（30/35dB, 7001格子） |
| [`exp043_3l.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_3l.yml) | `a492fa8cbf76e8189d62004252ed641c6a70b849` | EXP-043 search_3l.py（旧planned前提） |
| [`exp043_4l_one_shunt.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_4l_one_shunt.yml) | `91085275ecb9dc97fabbb409dfb855a7f14f302b` | EXP-043 search_4l_one_shunt.py |
| [`exp043_extra_modes.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_extra_modes.yml) | `29152d661a2b93f28fb9a17a6e7386f5d6e832f2` | EXP-043 search_extra_modes.py |
| [`exp043_gjm_q_vs_cap.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_gjm_q_vs_cap.yml) | `ef16fde7762c4f06ca411e9d9cb9f373fb5a3356` | EXP-043 diagnose_GJM_Q_vs_C.py（OFFSPEC含む） |
| [`exp043_k_vs_c.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_k_vs_c.yml) | `7899a08c0be9466c1767cfbb5390877daca6fe5e` | EXP-043 diagnose_k_vs_C.py |
| [`exp043_loss_budget.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_loss_budget.yml) | `06f2b3ba7d81b4699f5d5f5e43e08a2e8113c043` | EXP-043 analyze_loss_budget.py |
| [`exp043_manifest.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_manifest.yml) | `982b02f07a8f4422fb857fa2fa0686a9ced4aeea` | scripts/bootstrap_exp043_manifest.py（旧研究ブランチへのpush） |
| [`exp043_one_gjm_cp_refinement.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_one_gjm_cp_refinement.yml) | `d677e09c74ab57228ac89167f274d8c22c487a79` | EXP-043 refine_one_gjm_cp.py（多start、旧失敗記録） |
| [`exp043_passband_q.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_passband_q.yml) | `f757f0314928ee194148b542ece48b261e5600e0` | EXP-043 analyze_passband_q.py |
| [`exp043_pcb_gjm.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_pcb_gjm.yml) | `8f0f569d849fbedaffb910e5df35b37eb48c672d` | EXP-043 diagnose_pcb_gjm.py（OFFSPEC含む） |
| [`exp043_shunt_position.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_shunt_position.yml) | `26dd9dbef3d5a0083af07f73ebd649ba33390dea` | EXP-043 search_shunt_position.py |
| [`exp043_verify_3l.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_verify_3l.yml) | `0a6e85b0ee17379325c465d2112893a1d07df0dc` | EXP-043 verify_3l.py（独立枝電流MNA） |
| [`exp044_pi3l.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp044_pi3l.yml) | `b1b85a00851298e3996b5c809eb7387eafdb9ffa` | EXP-044 search_pi3l.py＋verify_pi3l.py |
| [`lpf-exp009.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp009.yml) | `d10e9f5bf9137d844159efb0c11a59c338c353c2` | EXP-009 sweep.py＋aggregate.py（Artifact/再開） |
| [`lpf-exp010.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp010.yml) | `d110761edb9506be782f059d72c703ab78a01173` | EXP-010 mixed_study.py＋summarize.py（Artifact/再開） |
| [`lpf-exp011.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp011.yml) | `c98b76779ceb3ddae8a41d93f412199417d84fe4` | EXP-011 compact_search.py＋aggregate.py（Artifact/再開） |
| [`lpf-exp012.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp012.yml) | `2c28d5bf8beb1c3d07da58171497a7b64db96213` | EXP-012 search_cost.py（4分割） |
| [`lpf-exp013.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp013.yml) | `02463e80d8bd89f98b9ec28b4f4f3e4b6a99ad00` | EXP-013 シェルに埋め込まれたPython heredoc（元YAMLが再現元） |
| [`lpf-p4-a-smoke.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-p4-a-smoke.yml) | `e1bdf722f2be7b08101316eb1a857b168f18a78f` | matching_limit/p4_batch.py（checkpoint保存→再開3 job） |
| [`lpf-p4-a.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-p4-a.yml) | `922e7cdfe97bfc04bb4664ae04192284019cea99` | matching_limit/p4_batch.py＋aggregate_p4_a_shards.py（手動shard） |
| [`lpf-target040.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-target040.yml) | `9bdb97ff365a626a614bc0198c04cfe419771a8b` | EXP-004 sweep_040.py＋summarize.py（Artifact/再開） |
| [`rft003-dense-replay.yml`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/rft003-dense-replay.yml) | `24bc4326b72cddf5bcb15a6ae30d5996a26f7a71` | verify_rft003_{5l_cost,7l_best,5l_1gjm_nearmiss}.py（旧試験、7001格子） |

## 退役前に把握した例外と再現の限界

- 28件のYAMLが直接指定している`scripts/`／`experiments/`配下の明示的な`.py`パスは、固定基準mainの追跡treeに存在することを**静的に確認**した。ただし依存先の再実行、数値一致、パッケージと環境の再構築は今回**未実行**。`lpf-exp013.yml`はPythonコードを`run`のheredocで直接記述するため、特に元YAMLが不可欠。
- `exp042_manifest.yml`と`exp043_manifest.yml`は**Git write権限**・特定の`research/`ブランチへのcommit/pushを含む。原定義をそのまま現在のmainや成果済みブランチで再起動することを推奨しない。個別worktreeやcopyで差分確認し、必要なときだけ許可して書き込む。
- `exp043_3l.yml`等の元preflightは`manifest.execution.status=="planned"`を仮定するため、元実験の状況が後日変わった場合は**元コミットに復元して検証**する。元の`planned`判定や当時のCI成功を現在の探索成功に読み替えない。
- `lpf-exp009/010/011.yml`, `lpf-target040.yml`, `lpf-p4-a.yml`等はGitHub Artifactsのcheckpoint復元・分割集計を利用している。**過去のArtifactが失効していれば、元runの途中からのビット同一再開は保証できない**。元YAML・スクリプトを復元した上で、新しいrunで再計算するか、Gitに保存された独立チェックポイントから再開条件を検証する。
- `exp043_gjm_q_vs_cap.yml`と`exp043_pcb_gjm.yml`には`OFFSPEC`比較も含まれる。**現行RF-T005適合の証明として扱わない**。歴史的RF-F001/F002/T003と現行正式RF-F003／試験RF-T005は混同しない。
- 最終値、考察、完全L/C/k・6設定可変C、制約・S2P SHA、保存元の失敗・中断・訂正情報は`experiments/`と`data/`に保持。CIジョブ定義や期間限定Artifact名の保存を数値証拠の保存と取り違えない。
- **EXP-004/005/009/011/012の元READMEは元manifestからSHA固定された一次証拠**。これらを旧workflow相対リンク修正のために書き換えると出典検証が失敗することを[PR #102 初回CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39120876568)で確認したため、**5件を元blobへバイト同一で復元済み**。元README中の退役済みworkflowへの相対リンクは歴史資料としてそのまま残し、閲覧者は**本ページの固定コミットリンク**からYAML・コマンドを回収する。旧UIの「Run workflow」案内も当時の説明であり、退役後に直接起動できるという意味ではない。

## Draft PRの受入条件

1. [Step Aの軽量スモーク](phase2_stepA_smoke_and_on_demand_checks_20261018.md) がPASSし、3つの残存workflow `audit.yml`／`reserve_experiment_number.yml`／`phase2_bc_wave1_consolidated.yml`を維持する。
2. **差分の削除パスは表の28 workflow YAMLに限定**。Python、実験結果、候補ベクトル、独立検証、JSON、固定S2P、制約は削除しない。
3. **manifestでSHA固定されていない**通常文書の削除先相対リンクだけを上記固定Git URLへ変更。**SHA固定の実験README 5件は原本として改変しない**。元相対リンクの参照先は本ページの固定Git版へ誘導し、未実行・未収束・失敗の歴史記録を維持する。
4. **28パスの一括退役・削除は2026-10-18のユーザー回答「承認します」により個別承認済み**。PR #102の最終headで軽量CI成功と差分範囲を再確認してからmainへ統合する。追加の監査workflowや巨大なSHA台帳は新設しない。

適用後の**目標**は31→3件（日常スモーク、EXP番号予約、歴史的出典照合の手動実行）。これは2026-10-18時点の旧提案であり、2026-10-26のActions探索継続・旧ローカル探索退役方針で置き換えられた。
