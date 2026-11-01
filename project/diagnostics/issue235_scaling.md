# Issue #235 / Stage 9B-1：尺度診断とopt-in実装

## 範囲・出典

診断先行、forward-only（実SLSQPの新規最適化0、EXP予約0）。基点main
`8e45cc38bf927977ee73eca89466cba133b46b95` のCI成功を確認後に着手。
Issue #233 / merged PR #234の3構成・9保存初期値だけを使用した。
既存の結果・manifest・RF条件は変更しない。Phase 2のまま。

- active formal: RF-F003 / `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba`
- 明示opt-in trial: RF-T008 rev3 / `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`
- 機械可読記録：[issue235_scaling.json](issue235_scaling.json)。各manifest/保存stage証拠のパス・byte SHA、完全初期ベクトルとt、vector/definition SHA、変数ごとのbox・値・相対差分幅・勾配感度を記録。
- Python3.12 / frozen uv環境。NumPy/SciPyバージョン・診断script SHAはJSON内。
  全evidence checkoutが必要。sparse環境では履歴診断をPASS扱いしない。

再現（最適化しない）：

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src uv run --frozen python scripts/diagnose_phase2_scaling.py > /tmp/issue235.json
```

## 観測（実装前診断）

SciPy 1.18.1のSLSQP既定値をsignatureから確認：絶対差分幅
`eps=1.4901161193847656e-8`、`ftol=1e-6`。従来callbackはmaxiter以外を指定しない。
物理ベクトルはnH/pF/kを含み、同じ絶対epsが同じ探索相対距離にはならない。
box幅は3L0GJMで0.18〜26.6、3L1GJMで0.18〜100、4L0GJMで0.2〜26.6。
幅100のGJMではeps/幅≈1.49e-10、幅0.18では≈8.28e-8。
固定kの幅0は差分対象外、tは独立のdB。

各初期値、粗2点×28不連続区間（56サンプル）で、全可変座標を内向き片側差分。
3幅は物理eps、box幅×1e-6、box幅×1e-4。
`dr/dz = box幅 * dr/dx` にそろえ、サンプル方向のmax-normを比較した。
表は基準「幅×1e-6」に対する勾配差の相対max-normを、さらに座標方向で最大化した値。
中心差分・解析微分との真値比較ではなく、曲率と丸めの両方が含まれる。

|EXP|構成|物理epsとの差|幅×1e-4との差|
|---|---|---:|---:|
|086|3L0GJM|1.479e-5|1.470e-3|
|087|3L0GJM|2.495e-4|2.478e-2|
|088|3L0GJM|4.727e-4|4.571e-2|
|089|3L1GJM|2.495e-4|2.478e-2|
|090|3L1GJM|1.454e-5|1.442e-3|
|091|3L1GJM|4.417e-4|4.272e-2|
|092|4L0GJM|2.216e-5|2.196e-3|
|093|4L0GJM|3.039e-5|3.006e-3|
|094|4L0GJM|2.148e-4|2.134e-2|

保存済み18stageのstatus/nit/nfev/格子/観測残差もJSONに出典付き転記した（再最適化なし）。
例：EXP-087は両stage status0だがH2最小29.99999989789343dBで、厳密30dB判定はFAIL。
ftolは複数の停止判定に関係し、厳密な全不等式非負や連続帯域適合の証明ではない。
EXP-086/093の非収束・巨大な負のtも、物理ILや可行性の証拠へ転用しない。
初期値のみの感度なので最終点付近の勾配安定性や収束改善は未確認。

## 最小実装・比較方法

`NormalizedEpigraph` は有限boxの物理変数だけをアフィン変換する。
可変座標は[0,1]、固定座標は[0,0]のゼロとして完全ベクトル内に保持、tは無界dB。
非有限・不正長・box逸脱・open lower一致・component/SPD失敗は例外。
clip、正のepsilonの捏造、物理修復はない。open lower閉包へSciPyが到達すると
このopt-in経路はfail-closedで停止する（従来経路の挙動は不変更）。

```python
from functools import partial
from lpf.phase2_models.staged_optimization import scipy_slsqp_stage

# 準備済みC1/C2のoptimize_stageへ渡す。これは本番の実行許可ではない。
callback = partial(scipy_slsqp_stage, coordinates="normalized")
# 比較候補だけ。採用済みの標準差分幅ではない。
comparison = partial(scipy_slsqp_stage, coordinates="normalized", finite_difference_eps=1e-6)
```

stageの入出力・warm start・vector SHAは常に物理座標。statusに座標系・指定epsと単位・
ftol不変更を記録。物理目的/残差・t・外部S2P・6設定/28区間・v2の240/120と回復規則を変えない。
正規化の有限差分では既定epsでも物理ステップがbox幅倍になるため、
同じepsという文字列だけで従来経路と同じ微分設定だと解釈しない。

mock比較は2/3点stageで0/0、8/0の同予算再始動、status9救済、4/9の非救済を確認。
物理/正規化の目的・残差・グリッド・status・予算・source/vector記録を照合する。
実回路のforwardは使うが、solverはmockであり収束改善の実証ではない。
既存の独立MNA・power・passivityゲートは不変更。今回の診断に対するdense1001・独立MNA・
power/passivityは全て`not_run`（ソフトウェア回帰テストの実施とは別）。

## 次の9B-2提案（未承認・未実装・未実行）

同じ9初期値・同じ2/3点・同じv2予算で、従来座標と正規化座標を対照とする。
差分幅候補は正規化座標で1e-8/1e-6をまず小さく比較し、1e-4は今回最大約4.6%の
勾配変化を観測したため曲率影響を別途診断する。新ftolや内部30.005dB guardを標準採用しない。
feasibility recoveryは別Issueで残差尺度、停止条件、予算を固定してから実装・比較する。
strict30適合・IL・最大負残差・stage停止原因・評価回数を別々に報告し、
適応格子（9B-3）やguard変更と同時に混ぜない。追加EXP/予算は別途ユーザー判断・G0/G1が必要。
SRF/Q(f)/EM/公差/実測、連続帯域、物理実現性、一般的収束率・大域最適性は未確認。
