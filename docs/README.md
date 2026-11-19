# docs/：旧文書パスと固定履歴

**現役の文章正本は[project/](../project/README.md)。** 運用は[project/instructions.md](../project/instructions.md)、RF数値は[registry](../rf/constraints/registry.json)。旧実験記録の再生・旧パス解釈は[legacy_git_replay.md](../project/legacy_git_replay.md)。

| 現存するもの | 用途と保持境界 |
|---|---|
| `methods.md`、`results.md`、`slsqp_iteration_policy.md`、`specification.md`、`governance/phase2_experiment_storage_policy.md` | いずれも現役`project/`を指す**symlink**。第二の数値正本ではない。廃止の判断は外部入口・EXP相対参照・実callerを確認してから |
| [chatgpt_project_instructions.md](chatgpt_project_instructions.md) | 旧URLから唯一の運用正本へ誘導する移転案内 |
| [旧W3統合資料（固定Git版）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/676e915cd82d14c4910aedbda435e6c308a00c37/docs/archive/w3_consolidated_documents_20261017.md) | D-001〜004の過去の承認・出典。内容の要点は[研究KB](../project/knowledge/legacy_evidence.md)に統合。旧W3監査は現行CIの依存ではない |
| [r2/EXP015_COMMON_MODEL_AUDIT.json](r2/EXP015_COMMON_MODEL_AUDIT.json) | EXP-015の旧数値監査原本。現存する[audit_exp015_common_model.py](../scripts/audit_exp015_common_model.py)との依存と再実行可能性を切り分けて判断 |

旧`docs/roadmap.md`の互換リンクも廃止した。現況は[Issues](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues)／[PR](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pulls)と現行コード・CI、研究結果は[results](../project/results.md)から確認する。

旧日付別レポートは[#352](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/352)で統合済み。逐語原文は[固定Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)から参照し、当時のCI・監査PASSを最新RF適合へ読み替えない。

**Issue #397は歴史資料の知見抽出後の削減を許可**しますが、現役外部参照・重要な正式実験証拠を未確認で削除しません。`project/diagnostics/`は作業中のため整理対象外です。
