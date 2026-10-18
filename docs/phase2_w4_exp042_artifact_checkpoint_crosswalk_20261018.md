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

## 実行済みの個票照合結果（2026-10-18）

[Actions CI 39091150899](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39091150899)で**10 ZIP／19 member**を元バイト・member SHA-256・ZIP CRC・全Git追跡ファイルの実バイトSHA-256と比較した。**内容のバイト完全一致は1件のみ**で、その1件は0 byteの`python_stderr.txt`（別実験の空ログと同一）だった。これは研究成果を重複排除できることの証明ではない。元ZIPと選別済みGit checkpointは**別の出典として両方保管**する。

| 元Artifact内の記録 | Git側の候補・検証 | 実行した照合の結果 | 判定 |
|---|---|---|---|
| `target_30.json` | `selected_checkpoints_rft005.json`のEXP042-30m005 | **29ベクトル成分一致**、最悪IL/H2/H3一致、solver_success=falseも一致 | 同じ保存段階の選別候補。ただし元Artifactの独立保管は継続 |
| `target_35.json` | 同ファイルのEXP042-35m005 | **別の最適化段階**。元ZIPはsolver_success=false、Git選別はtrue。29要素差最大**0.259916758**、記録メトリック差最大**0.001251304 dB** | **代替不可**。元途中段階と選別候補を両方保持 |
| `verification_7001.json` | `verified_7001.json` | 両候補とも28区間×7001点・84独立MNA点の記載が一致、IL/H2/H3記録差最大**7.11×10⁻¹⁵ dB** | **保存済み報告の整合**。新しいRF再計算ではない |
| `area_pcb_both.json`, `area_pcb_cf1.json` | `checkpoints/pcb_both.json`, `checkpoints/pcb_cf1.json` | 29要素ベクトル、保存メトリックとも一致 | 選別済みcheckpointに対応。ただし元ZIPは保持 |
| `area_cf1.json` | `checkpoints/cf1.json` | 29要素差最大**0.010156763**、保存メトリック差最大**1.58×10⁻⁵** | **異なる局所解／stage**。削除・同一化不可 |
| `area_cf2.json`, `area_both.json`, `area_pcb_cf2.json`と各`*_independent.json` | `checkpoints/cf2.json`, `checkpoints/both.json`, `checkpoints/pcb_cf2.json` | **該当する想定パスは現行mainに存在しない（6 member）** | ZIPが現存する一次成果物。選別checkpointの存在を主張しない |
| `driven_passband_magnetic_q.json`およびstdout等 | `passband_magnetic_q_probe.json`ほか | 診断変種の名前・参照先を関連付けたが、全データ同値は未確認 | 再現・失敗解析用の別の資料として保持 |

**確認済みの差異は数値探索の別段階として保留する。** 「同じ候補ID」や「数値がほぼ一致する」ことは、バイト重複・復元可能性・代替保全を意味しない。元runでの開始条件・seed・反復制限、各Artifactの選別過程をさらに確認する必要がある。存在しない3つのチェックポイントを新規数値として復元・捏造しない。

## 重要な判定上の区別

1. `target_35.json`は、元ZIPのselectedに`solver_success=false`（iteration limit）と記され、Git選別`EXP042-35m005`は`solver_success=true`。L値・29要素ベクトルも異なる。これは**元runの異なるstageが保管された可能性**として個別保持し、同一実行結果や矛盾と直ちに断定しない。最終候補の数値はGit選別`verified_7001.json`を出典とする。
2. `verification_7001.json`のメタデータとGitの`verified_7001.json`には同一候補IDが記録されている。保存値の一致は検証スクリプトで定量判定するが、物理Q(f)・SRF・EM、連続帯域の厳密極値、実測を証明しない。
3. **「同じ候補を表現する」ことと「ZIP元バイトが再生成可能」は別問題**。元ZIPは2027-01-15期限のため長期保全済み。原研究source・run・checkpoint・旧46保護・元ZIPのどれも承認なく削除しない。

## 実行・記録状態

- 元Artifact ZIP保全とSHA/CRC：**PR #84で実行済み**。
- 全19memberのbyte比較、6variantのベクトル比較、30/35dB stageの違いと7001点記録比較：**実行済み**（[W4専用CI 39091150899](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39091150899)：SUCCESS）。[個票CSV](../data/repository_reviews/w4_exp042_member_crosswalk_20261018.csv)と[要約JSON](../data/repository_reviews/w4_exp042_crosswalk_summary_20261018.json)を保全し、以後のPRでも実ファイルとの完全一致を検査する。
- 新しいRF最適化・高密度MNA計算：**実施しない**。
- 個別削除許可・削除実行：**どちらも0件**。

**削除可否の未決項目：** 元ArtifactとGit資料の意味的非互換・元run履歴・失敗時の解析ログ・復元に必要な元CLI/依存を含めてレビューするまでは、移動や削除の根拠としない。
