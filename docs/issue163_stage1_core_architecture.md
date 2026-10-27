# Issue #163 — Stage 1 共通回路計算基盤：構造整理・公開API・完了基準

**状態：Stage 1 進行中。** 本書はPR #164の実装レビューと、Stage 2へ移る前の完了判定に使う設計方針。履歴EXPの変更や、新規EXP探索、Phase 3の承認を意味しない。RF数値条件・外部S2P・SLSQP予算の変更は含めない。

## 1. 結論：Stage 1の共通コアを先に完成させる

57項目を全部切り出してから進むのではなく、**回路の定義・RFポリシー適用・計算可能な行列・単一の公開API**というStage 1の閉じた単位を完了させる。その後にStage 2の独立MNA・高密度RF検査、Stage 3の最適化、Stage 4のトポロジー探索、Stage 5の実行基盤を積み上げる。Stage 1以降で使う最小の「部品配置とパラメータの意味」を先に固定しなければ、新しい実装ごとに相互変換が増える。

**Stage 1に含める**：接続グラフと枝方向、L/C/Q/符号付きk、部品型・物理L順序、6設定パラメータと固定／可変／追加寄生の区別、RF制約認証と候補の部品制約判定、周波数点上のforward計算、エラー処理、履歴数値パリティ、公開APIとドキュメント。

**次段階へ切り分ける**：独立枝電流MNA／電力収支／dense H2・H3／RF達成判定（Stage 2）、seed/SLSQP・収束状態（Stage 3）、グラフの列挙・同値重複排除・面積Pareto／候補登録（Stage 4）、Actions/Pi Code実行・manifest・resume（Stage 5）。既存の`port_parasitics.py`等は再利用し、必要以上に再実装しない。

## 2. レイヤーと単一の利用入口

```text
NEW EXP script / future optimizer / future Actions runner
                  |
                  v
phase2_models.api  [STABLE PUBLIC API]
  CircuitDefinition + build_nominal_circuit(policy, definition)
                  |
                  v
  NominalCircuit (immutable configured facade)
      |                |                    |
      v                v                    v
 schema/values   validate_components    forward_evaluator
   [L,C,k]         [approved RF policy]       |
      |                |                     v
      +----------------+------------> coupled_lc.CoupledLCEvaluator
                                          |
                              nodal L/C stamp + Schur 2-port
                                          |
                              28 intervals x 6 settings + S2P
                                          |
                             sampled summary (NOT RF certificate)
                  |
                  v
          Stage 2 independent branch-current MNA
              (different algorithm; not shared solver)
```

今後の新規EXPでは、`phase2_models.api`を唯一の推奨入口とする。EXP名を持つ`exp042.py`/`exp055.py`/`exp058_*.py`は数値パリティ用の**互換アダプタ**であり、将来の回路定義の親クラスや探索ランナーとして使用しない。

- **`CircuitDefinition`**：`InductorTree`（端子、枝順・向き）と`CapacitorPlacement`、明示的なL部品型、物理配置順、kスロット、固定C型、可変C役割を保持する。値や試験RF制約を隠して持たせない。
- **`build_nominal_circuit(policy, definition)`**：正式に解決されたtrialのfingerprintとモデル・枝数を検証し、試験条件別のCネットワークを正確に構築する。未対応RF-F003/RF-T006は**黙って別ポリシーとして扱わず拒否**する。
- **`NominalCircuit`**：`schema/decode/encode`、`validate_components`、`evaluate_sampled`、`forward_evaluator`を一貫して提供。`forward_evaluator`は数値探索向けの未チェックkernelであり、候補認定を意味しない。
- **`CoupledLCTopology` / `ParameterVectorSchema` / `CircuitValues`**：EXP固有ではない計算表現。展開後のC枝順は`[fixed, variable(setting), IC-fixed, constant-parasitic]`。平坦化パラメータ順は`[L, Cfixed, k, IC-fixed, 6 x Cvariable]`。枝／値のインデックス意味を明示し、物理C設置0枝・OFF=0を保持する。
- **試験ポリシー実装**：RF-T005とRF-T007は`rft005_t007_policy_circuit.py`、RF-T008 v3は`rft008_policy_circuit.py`。`nominal_inductors.py`、`rft008_layout.py`、既存の`constraint_versions`/`trial_shunt_dtc`/`trial_ic_fixed_c`/`trial_pcb_pattern_c`/`validation`を使用する。**RF規則を新コード内の別定数として増やさない。**

外部S2Pと帯域処理は`_grid.py`→`port_parasitics.py`に依存する。既存の`lpf.evaluate`との将来的なA01–A03整理では、**キャッシュ／S2Pハッシュ／ABCD／源負荷規則の二重実装は禁止**する。

## 3. RF条件の違いを「回路の型」として扱う

| 特性 | RF-T005 | RF-T007 | RF-T008 v3 |
| --- | --- | --- | --- |
| 可変C設置数 | 0～3 | 0～3 | 0～2 |
| 可変C | 各0～3pF/Q35 | 各0～3pF/Q35 | 各0～3pF/Q35 |
| 接地DTC常設寄生 | なし | 設置接地枝ごとに0.5pF/Q40 | **なし** |
| IC内固定C | なし | なし | 設置DTCと1:1、Q60 |
| IC内固定C値 | ― | ― | Hot-GND 0.5～3pF、Hot-Hot 0.2～3pF |
| PCB-C | 0.02～0.2pF/Q40、最大3個 | 同左 | 接地0.02～1pF/Q60、Hot-Hot 0.02～0.2pF/Q40、計最大3個 |
| GJM01 | Q80、最大100pF | 同左 | 同左 |

*全てPhase 2の公称モデル。GJM01は**形式上の0.02pF最小値を持たない**。その値はEXP-058の探索用下限にすぎない。新規政策ゲートと互換評価器の探索境界を分離済み（`gjm_lower_pf`をEXP互換ラッパーで明示）。チップ面積には形式的な6単位ハード制限を復活させない。*

LシリーズはRF-F003の明示範囲が確定したLQP02HV/HQ/PCB_LについてポリシーからQ・L範囲・隣接k・SPDを確認。未確認LQP01等のL範囲、実物Q(f)、SRF、EMは自動承認しない。

## 4. API利用の基本手順

```python
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree

p = load_constraint("RF-T008", allow_trial=True)
var = ((0, 3), (1, 2))
definition = CircuitDefinition(
    inductor_tree=InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
    inductor_types=("LQP02HV",) * 4,
    physical_order=(0, 1, 3, 2),
    coupling_pairs=((0, 1), (1, 3), (3, 2)),
    capacitor_placement=CapacitorPlacement(
        5, ((0, 1), (4, -1), (1, 2), (0, 3)), var, var
    ),
    fixed_c_types=("GJM01", "PCB_PATTERN_C",
                   "PCB_PATTERN_C", "PCB_PATTERN_C"),
    variable_roles=("bridge", "bridge"),
)
circuit = build_nominal_circuit(p, definition)
values = circuit.decode(saved_vector)
assert len(circuit.encode(values)) == len(saved_vector)
component_check = circuit.validate_components(saved_vector)
sampled = circuit.evaluate_sampled(saved_vector, points_per_interval=3)
# これだけではRF適合認定でも独立MNA PASSでもない。
```

値、単位、型、枝数が合わない場合にはエラーとする。ルーティンが無条件で真の「RF検証済み」フラグを返してはいけない。部品制約検証・forwardの有限サンプル・独立MNA・dense RF・最適化収束・物理検証をそれぞれ独立状態で管理する。

## 5. PR #164監査で判明した整理課題

1. **公開APIの断片化**：これまでT005/007とT008を別クラスから構築。今回`api.py`の共通facadeで統合した。旧EXP由来モデルを新規EXPに公開し続けない。
2. **実験探索境界と政策境界の混同**：RF-T008のGJM01下限0.02pFは実験固有。`RFT008CapacitorLayout`の形式的な値確認から切り離し、互換ラッパーは明示的に0.02pFを維持。将来の固定値上限／optimizer境界にも同じ区別が必要。
3. **roleの意味の弱さ**：現在は`"series"`か`"bridge"`を利用者が与え、`validate_variable_c_connections`はその役割と端子の整合を見ている。しかし**そのCが主信号経路に対し本当にseries/bridgeなのかは、電気的・物理的なグラフ解析でまだ証明していない**。危険な自動推論は避け、Stage 1完了前に役割の形式的意味と判定範囲を決定する。
4. **対象の幅**：現在は3L/4Lの凍結事例を回帰。任意ノード・L種類の正規化、固定C多重枝の扱い、単一設定での開放分岐、接続異常時の例外にはさらに境界テストが必要。
5. **実装重複**：`SampledExternalEvaluator`、`lpf.evaluate`、`port_parasitics`の使用範囲、S2Pロード回数・固定S2PファイルのSHAをテストで明確にする。現時点でこれらを完全に一本化したと主張しない。
6. **APIの安定性**：既存`exp*.py`互換ラッパーを削除・リネームせず、新規コードだけ`api.py`を利用。パブリックな入出力と例外・単位の仕様書を固定し、内部実装は自由に改善可能とする。
7. **検証の独立性**：Stage 1のforwardパリティを、Stage 2の独立branch-current MNAと呼ばない。共通の`CoupledLCTopology`という*入力データ*の共有は許すが、Y縮約や行列の中間結果をMNAで再利用しない。

## 6. Stage 1を完了と認定するDoD

全項目チェック後にのみIssue #163のStage 1を完了とする（現時点では**未達**）。

- [ ] **S1-01 公開契約**：`api.py`を入口にT005/T007/T008の全代表構成を表現でき、EXP固有実行スクリプトへの依存・グローバルpatchがない。サンプルコードと型／単位／例外の説明が一致。
- [ ] **S1-02 不変回路データ**：向き付きL枝、source/load端子、GND、C並列・接地、物理L順序、結合kスロット、0～N個の合法枝を混線させずに表現・検査。
- [ ] **S1-03 制約認証**：対応するRF trialのresolved policyが現行registryと一致。未対応のRF-F003/T006は明示拒否。無断で旧 trial・新 trial のパーツを合成しない。
- [ ] **S1-04 C物理モデル**：T007の各接地DTCごとの0.5pF/Q40、T008の各DTCごとのIC固定C/Q60、OFF状態、Q35、PCB-C接地／Hot-Hot差、GJM探索下限／形式的範囲の区別。
- [ ] **S1-05 L物理モデル**：現在の明示シリーズの範囲とQ、chip順序、名目非隣接k=0、混合PCB k、SPDをチェックし、未仕様のLシリーズを非対応として示す。
- [ ] **S1-06 可逆パラメータ**：`decode/encode`がT005/T007/T008の全枝数、6設定、固定C不変、T007常設枝、T008IC固定枝、旧placeholder移行について可逆または明示変換／拒否。
- [x] **S1-07 接続役割の整理**：shunt/series/bridgeの意味を定義し、検査可能なものを検証、未証明の物理分類をポリシー適合と混同しない。
- [x] **S1-08 数値パリティ**：EXP-042/043/055/058の保存済みベクトルと28×6格子上で許容誤差（まずabsolute 1e−9dB）以内、外部50Ω・60−j40Ωと固定入出力S2Pを保持する。代替L/Cグラフでinstance間干渉がない。
- [x] **S1-09 堅牢性**：不正な接続/値/Q/k/非SPD/非有限入力を拒否し、単位取り違え・S2Pの不正データ・意図しないキャッシュ汚染を検出。正規化はnode 0始まり・GND=−1で一元化。
- [ ] **S1-10 証拠とCI**：新旧互換回帰・数値パリティ・制約チェック・証拠SHA監査をCIでPASS、コード例とDoD文書が更新済み。旧EXPソース/manifest/実験結果は不変更。

**S1-07のグラフ上の役割判定について**：直列／橋絡の区別が端子だけで一意に定まらない構造がある場合、無理に自動分類しない。物理主経路との対応を明示した別入力と検証手順を定義し、未証明は`role_unverified`として最終候補ゲートへ送る設計でよい。

## 6.1 変動C接続role監査（S1-07の電気的証拠）

`src/lpf/phase2_models/role_audit.py`は、**RFポリシーがroleの申告を許しているか**という既存`validate_variable_c_connections`の確認とは別に、接続Lツリーで証明できる範囲を返す。新EXP用公開`NominalCircuit.connection_role_audit()`で利用する。

| 宣言 | Lツリーで検証できる証拠 | 扱い |
| --- | --- | --- |
| `shunt_to_ground` | 実際に一方がGND（−1） | 電気接続としてverified |
| `bridge` | Hot-Hot両端間にLツリー経路があり、Cはその経路のchord | **電気的な経路を跨ぐことのみ**verified（物理的ブリッジ実装の保証ではない） |
| `series` | Lが全hotノードの接続ツリーを形成するため、C挿入が必須信号経路上にあるとは証明不能 | `role_verified=False`、未証明indexを返し、候補昇格を保留 |
| 端子・roleの不一致 | GND端子にbridge/series、Hot-Hotにshunt等 | 接続不正として拒否 |

`validate_components`は承認済み部品制約の`component_policy_pass`を**変更せず**、`connection_role_audit`と`connection_role_promotion_blocked`を別々に付記する。`evaluate_sampled`にも同じ情報を反映する。seriesがRFポリシー上**許可される場合**も、シリーズの物理配置が未証明ならroleの未検証フラグを立てる。加えて、**Stage 1は独立MNAとdense RF評価を実行しない**ため、roleが完全に電気的検証済みであっても`candidate_promotion_blocked=True`を常に返し、`promotion_blockers`に`independent_mna_not_checked`と`dense_rf_not_checked`（該当時`connection_role_unverified`）を明記する。単一のブール値でRF適合済みに誤解させない。

この証拠は**可変Cの電気接続グラフだけ**の判定であり、PCB/GJM固定Cの製造可能性、主信号経路の物理定義、直列スイッチ等を証明しない。追加の物理主経路定義・実装証拠が必要な回路ではStage 2/4の候補検証に引き継ぐ。新しいRF数値上限・直列配置禁止を導入したわけではない。

回帰：`tests/test_phase2_connection_roles.py`（5件、相異なるseries/bridge宣言でのnumerical model一致、未証明seriesの候補昇格保留、shunt/bridge不整合拒否、0枝の空監査、インスタンス間の分離）。

### S2P・格子・cache監査（S1-09の一部）

`tests/test_phase2_s2p_grid_cache.py`で、`port_parasitics._load_verified`がSHA-256/50Ω-RIを既存機能で検証し、`get_two_port_s`がキャッシュ内部を別呼び出しへ可変参照として返さないことをチェックする。S21=0、補間範囲外、非有限周波数、改ざんされたS2P SHAは拒否。28帯域区間×3点／6設定のラベル・境界、別評価器のABCD行列非共有も確認する。`_grid.SampledExternalEvaluator`はpointsに整数以外・bool・0以下を明示拒否する。S2Pの再実装や正規データの書換えは行わない。

**S1-09は完了扱い**：上記のS2P/cache検証に加え、後節の型付き数値失敗診断と5L合成境界テストを追加し、CIで確認した。極限Q(f)・物理Sパラメータの追加検証はStage 2以降の物理/RF検証対象であり、本DoDの数値入力・行列異常対応と混同しない。

### S1-09 共通forward失敗の分類（2026-10-27）

`src/lpf/phase2_models/numerical_diagnostics.py`の
`CircuitNumericalError(ValueError)`は、次段階の最適化器が失敗理由を
文字列メッセージのパース無しに保持できるよう、
`code`と（特定できた場合のみ）`sample_index`を明示する。

| `code` | 区別する異常 |
| --- | --- |
| `mutual_nonfinite` / `mutual_eigensolve_failed` / `mutual_not_spd` | 相互L行列・SPD検証 |
| `inductor_solve_failed` / `inductor_admittance_nonfinite` | 結合L admittanceの解法 |
| `node_nonfinite` | L/Cからの節点アドミタンス計算 |
| `schur_solve_failed` / `schur_nonfinite` | 内部ノードのSchur縮約 |
| `transfer_singular` / `abcd_nonfinite` | Y→ABCD変換 |
| `cascade_nonfinite` | 固定入出力S2Pとの積 |
| `gain_denominator_invalid` / `gain_nonfinite` / `il_nonfinite` | 端子利得・IL |

構成の事前入力エラー（非有限vector、非整数setting index、
不正ポート、設定数の不一致、容量・Qの不適合）は原則`ValueError`、
型契約違反は`TypeError`を維持する。数値特異点を勝手に修復したり、
悪条件行列の失敗をRF実現不能の数学的証明と解釈したりしない。
`sample_index`は最初の異常サンプルを確定できた場合のみ設定する。

`tests/test_phase2_numeric_diagnostics.py`は保存済みEXP-055
ベクトルと専用の合成行列で、非SPD、L solve失敗、
Schur特異、伝達admittance特異、非有限外部cascade、
設定／周波数／非有限vector、グラフの自己ループ・非連結・無効port、
平行C枝、5L（6 hotノード）forward演算を確認する。
**5Lは合成数値動作テストであり、承認済み部品・RF性能達成を意味しない。**

入力50Ω／負荷60−j40Ωは従来の公称RF値のままで、
forwardカーネルの旧ハードコードを廃止して、
**resolved policyの`source_ohms`と`load_ohms`から取得**。
非有限／受動でない／周波数依存の未対応インピーダンスは
推定代用せず拒否する。`port_parasitics.py`の50Ω RI S2P
正規化・SHAをそのまま使用する。旧EXP-042/043/055/058との
完全なforward数値パリティをCIで維持する。

## 7. 実装の進め方

- **PR #164：Stage 1 core（既存）**。一貫した公開facade、L/C/Q/k正規化、T005/T007/T008条件差分、凍結数値パリティまで整える。途中の実験系統別`exp*.py`は互換・テスト用途へ位置付けを固定。
- **残作業は小さな後続PR**に分離：グラフ上のrole検証、エラー／cache・S2P重複の整理、全枝数境界テスト。Stage 1 DoD合格前にStage 2の汎用独立MNA開発へ進まない。
- Stage 1をmerge可能にするために、PR #164のfeature追加を無制限に増やさず、CI PASS確認後にレビューを行う。Issue #163はStage 1のDoDが完了するまでOPENのまま。
- Stage 2以降は**Stage 1の公開APIのみ**を呼ぶ。別のEXP固有`Evaluator`や`sys.path`挿入を新規コードへ持ち込まない。

**未実施**：新規EXPの予約・最適化・密格子RF探索・独立汎用MNA・物理Q(f)/SRF/EM・Phase 3。既存履歴の再分類は行わない。
