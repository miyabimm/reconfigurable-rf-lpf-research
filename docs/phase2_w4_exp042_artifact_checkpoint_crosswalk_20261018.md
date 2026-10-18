# Phase 2 W4：EXP-042 Actions元ZIPとGit候補原本の対応監査（2026-10-18）

> **作業範囲：** 旧RF-T005（正式RF-F003とは別の3可変C試験条件）のEXP-042について、[Gitにバイト単位で保全した10 ZIP](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)の内部ファイル19件と、[EXP-042元Git資料](../experiments/chatgpt_topology_search/runs/EXP-042/README.md)、checkpoint、manifest、現行候補台帳の出典を照合する。これは**既存の記録同士の照合**であり、回路計算・最適化や独立MNAを再実行するものではない。Phase 2維持、Phase 3未承認。

## 元データ・照合範囲

- main基準：`87717a55673cb1cff43474a77d00088106b04c0c`（[PR #84](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/84)で10 ZIPの期限超え復元性を検証後）。
- 元ZIP10件／内部19 memberは[保全スクリプト](../scripts/preserve_exp042_actions_artifacts.py)で、Gitに埋め込んだZIPバイト、ZIP SHA-256、全member SHA-256・CRCを再照合。
- [W4対応スクリプト](../scripts/audit_w4_exp042_artifact_checkpoint_crosswalk.py)は、Gitの**全追跡ファイルを実バイトSHA-256**で逆引きし、内部memberと完全同一のGitファイルが存在するかを記録。同じ数値があることと、元Artifactと**同一バイトであることは異なる**。
- 試験SLSQPの`target_30.json`/`target_35.json`は[選別29要素checkpoint](../experiments/chatgpt_topology_search/runs/EXP-042/selected_checkpoints_rft005.json)と、**最適化stage・solver_success・29成分ベクトル・有限格子数値**を別々に比較。
- 28×7001と84独立MNAの元`verification_7001.json`は、[選別済みGit検証記録](../experiments/chatgpt_topology_search/runs/EXP-042/verified_7001.json)の同じ候補ID・区間数・格子数・MNA点数・IL/H2/H3に限り比較。値の一致は**保存記録の整合**であり、新しい独立解析を実行した証明ではない。
- 面積variantの`area_*.json`と`*_independent.json`は[チェックポイント](../experiments/chatgpt_topology_search/runs/EXP-042/checkpoints/pcb_cf1.json)など6変種の元Git記録に対応づけ、**29要素・保存された密格子値・84点記録**を比較。診断用`driven_passband_magnetic_q.json`は[GitのQ診断](../experiments/chatgpt_topology_search/runs/EXP-042/passband_magnetic_q_probe.json)に由来を紐付けるが、全内容の同一性を推測しない。
- 比較結果を個票CSVと要約JSONに保存。出典のステージが異なる場合に新しい方で上書きしたり、許容差一致だけで重複削除したりしない。

## 重要な判定上の区別

1. `target_35.json`は、元ZIPのselectedに`solver_success=false`（iteration limit）と記され、Git選別`EXP042-35m005`は`solver_success=true`。L値・29要素ベクトルも異なる。これは**元runの異なるstageが保管された可能性**として個別保持し、同一実行結果や矛盾と直ちに断定しない。最終候補の数値はGit選別`verified_7001.json`を出典とする。
2. `verification_7001.json`のメタデータとGitの`verified_7001.json`には同一候補IDが記録されている。保存値の一致は検証スクリプトで定量判定するが、物理Q(f)・SRF・EM、連続帯域の厳密極値、実測を証明しない。
3. **「同じ候補を表現する」ことと「ZIP元バイトが再生成可能」は別問題**。元ZIPは2027-01-15期限のため長期保全済み。原研究source・run・checkpoint・旧46保護・元ZIPのどれも承認なく削除しない。

## 実行・記録状態

- 元Artifact ZIP保全とSHA/CRC：**PR #84で実行済み**。
- 全19memberのbyte比較、6variantのベクトル比較、30/35dB stageの違いと7001点記録比較：**本PRのGitHub Actionsで実行し、個票と集計を固定する工程**。成功後にこの節を結果で更新。
- 新しいRF最適化・高密度MNA計算：**実施しない**。
- 個別削除許可・削除実行：**どちらも0件**。

**削除可否の未決項目：** 元ArtifcatとGit資料の意味的非互換・元run履歴・失敗時の解析ログ・復元に必要な元CLI/依存を含めてレビューするまでは、移動や削除の根拠としない。
