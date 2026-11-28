# #537 4段階CLI 機能smoke（非正式EXP）

## 条件・実行

`tests/fixtures/issue537-staged-smoke.json` は経路通過のためだけの緩いfixtureで、科学的推奨や実用予算ではない。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、#529の4L2C definitionおよびGJM01上限10 pFのbounds（SHA `4a72989fbbc1db6ba73719dae9c85f7dc82e18d4e91402d316c60cba7e64525e`）、元seed 2001–2003。3→2→最大2→全候補、Search上限3/5/5/5、Search/Terminal格子70/476・196/28028、Terminal独立MNA 2/84点、CP1000。Search MNAは未指定。最悪予約は48 RF forwards（Search 39 + Terminal 9）、63,378 requested samples、182独立MNA samples。全6設定・28区間、固定S2P・外部ポート。

ソースHEAD `388fc961d67230970abff56b01637257e1f6e0c0`（source SHA `36bc2a4f36939a43133d7614ef38b0ad099573650286c2a63d73aa3aad94ea44`、記録されたsource filesと空のdirty patchを監査）。smoke後に、完了済みphaseのledger消失・照合不良をunknownとして後段へ進めないSTOP境界を追加し、非RFテストで確認した。**その修正後HEADでRF smokeを再実行していない。** スレッドは全1、plain、標準CLIを**1回のみ**実行した。`lk` 指定でもTRF Search evaluatorの実効cacheは既存Workerによりoff。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/run_rf_search.py develop-staged \
  --config tests/fixtures/issue537-staged-smoke.json \
  --output /tmp/issue537-rf-smoke-ctp6qjYh/run --rf-cache-mode lk
# 既存の保存結果に対する、RF forwardなしの独立した記録照合:
uv run --frozen python project/diagnostics/issue537/audit_smoke.py \
  /tmp/issue537-rf-smoke-ctp6qjYh/run
```

再現コマンドは当時のソースHEADとfixture、未存在の出力先を要する。**上記は実行記録であり、追加の科学探索・再実行を許可するものではない。** raw/ledger/config/manifest、stdout/stderr、exit、監査JSONは `/tmp/issue537-rf-smoke-ctp6qjYh/` に保持（永続保管は未保証）。監査のコンパクトな出力は [`smoke-audit.json`](smoke-audit.json)。

## 観測と検証

- CLI exit **4**、全4段階・全9 jobs完了。discoveryはseed 2002/2001を順位順に選び、exploitationおよびrefinementで両候補を継承。discoveryは緩い目標に到達、他phaseはforward上限。refinement両seedとも数値未収束のため再現目標未達。探索不能や大域最適性の証明ではない。
- 実消費は48 forwards / 63,378 requested RF samples / 182独立MNA、すべてreceipt照合済み。unknown/released/not_startedはいずれも0。追加retry・再探索なし。
- `audit_smoke.py` はphase Plan/ledgerとJob receipt全raw bytes/checkpoint、sourceとthread、元seedと前段vector/SHAの一致、全6設定と28別区間、物理部品・接続、完全L行列SPD、Terminal受動性・電力保存、独立MNA spotの状態、予約・実費用を照合しPASS。初期・終端SHAと各receipt SHA・実消費は `smoke-audit.json` と元rawを参照。独立MNAは指定spotのみ。
- Terminal有限格子での全候補のRF適合は未達。格子間・連続帯域、SRF、Q(f)、EM、ばらつき、実測、物理実装可能性、正式RF適合は保証しない。少予算の機能確認を探索手法の性能比較に使用しない。

## 独立レビュー後の修正

PR #538の独立レビュー指摘に対応し、上位ledgerで凍結Planの全Jobと台帳行の件数・識別・予約・完了状態を照合する。欠落行は未使用予算ではなくunknownとし、次phase開始前にも確認する。正常な少数候補の未予約分は解放する。非RF回帰テストを追加。追加RF smokeは実施しない。
