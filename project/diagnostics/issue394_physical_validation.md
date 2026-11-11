# Issue #394: 物理検査経路と限定検証

## 責務と重複

| 箇所 | 固定・候補依存の扱い |
|---|---|
| `physical_bounds` | policyのL/C/6設定Cvおよび物理順序・部品型別kの厳密な閉区間。定数Cはschemaに保持 |
| `validate_values` → `check_nominal_inductors` → `validate_inductor_coupling` | 固定情報、schema、role、各値域、PCB数と全L-SPDを検証し、保存向け物理診断を作成。公開APIは維持 |
| `CoupledLCTopology.matrices` | 毎RF forwardの全結合L行列について非有限・固有値・悪条件を拒否。SPD閾値は不変更 |
| `MinimalWorker` | 開始時に上記の完全検査とboxを確定。外部入力・solver出力はbox検査、出力は完全検査も実施。Hybrid callbackではbox再構築・policy照合・前段SPDを繰り返さない |
| `window100` 通常search | 開始時完全検査、候補毎に凍結物理box検査、RF Core SPD。新しい科学順位bestに限り完全検査と物理診断を生成。追加RF forwardなし |
| legacy、window debug/spot、Selection/Terminal/anytime | 保存・readback・独立検証の契約を優先して従来の詳細検査を維持 |

boxの対象外である接続・role・物理順序・Q・PCB数・固定/IC/定数C整合性は、開始時のモデル構築と完全検査で維持する。未指定結合はゼロ、指定kはpolicy loaderが旧abs制限と閉区間を照合し、非隣接chip kはゼロ。SPDは候補依存なのでRF Coreで毎回判定する。従来validatorのk比較にある1e-12の許容よりも、physical boxは厳密な閉区間を先に要求する（従来どおり）。候補をclip/修復しない。

通常window searchの不正SPDは前段ではなく**予約・forward開始後**に検出され、開始済みsampleはrequestedに計上され得る。RF失敗としてSTOPし、未確定windowと親予約を保持する。これは#394で承認された変更であり、予算上限・atomic保存・readbackの緩和ではない。詳細経路の前段拒否は維持する。MinimalWorkerには永続台帳がない。

## 検証の範囲と残課題

対象テストは、合法候補の旧新RF応答/requirements/Hybrid、全座標の閉区間端点と直外、全6設定、型/形状/NaN/Inf、定義・policy不一致、直接RF CoreのSPD閾値、window best物理証拠、開始後SPD失敗時の課金とSTOP、独立MNA・電力/受動性関連の既存回帰を含む。具体的なコマンド・結果はPRを参照。有限テストで連続周波数・EM・Q(f)・SRF・公差・実測の保証はしない。

実RF A/Bはユーザー承認後、旧新各3回・計600 forward／42,000 samplesで実施。[条件・原記録・結果・限界](issue394_ab/README.md)を参照。6 runとも未収束。MinimalWorkerの限定計測であり、保存付きJobの性能やRF認定を意味しない。
