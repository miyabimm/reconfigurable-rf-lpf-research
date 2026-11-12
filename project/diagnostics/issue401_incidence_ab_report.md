# Issue #401: capacitor incidence先行準備候補（不採用）

凍結C incidenceをtopology初期化時に一度生成する候補を実装し、同一条件のplain旧新比較を実行した。旧HEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`、新HEAD `411110f8838d2a4889f64fc4e3393cc5beb919db`。対象実行source差分は `src/lpf/rf_core/coupled_lc.py` のみ。両方RF-T008 trial/full_lpf、Plan・grid・S2P・seed1002・100 nfev、70 samples、CPU affinity 0、BLAS/OMP/MKL各1 thread。`issue401_incidence_ab_raw/freeze.json`にsource identity・実行順・script SHAを固定。

warmup各1＋測定各10、旧新新旧×5の別process、合計22 run／2,200 forward／154,000 samples（nfevより算出）。全solver出力一致、全run予算切れ・未収束。直前の条件凍結、各runのstarted、stdout/stderr/returncodeは[原記録](issue401_incidence_ab_raw/)を参照。

| 指標 | 旧 中央値 [範囲] ms | 新 中央値 [範囲] ms |
|---|---:|---:|
| solve wall | 93.327 [90.408, 112.107] | 92.645 [89.310, 108.084] |
| solve CPU | 93.316 [90.411, 111.939] | 92.646 [89.309, 108.030] |
| setup wall | 249.563 [244.751, 271.659] | 258.508 [250.271, 272.495] |

solve中央値差は約−0.7%、順番対応差の中央値 −0.526 ms、範囲 −22.797〜+13.282 ms。負荷・外れ値等の変動に対して差が小さく、速度改善は未確定。KISSの観点からこの候補は**revertし不採用**。候補回帰では5 RFモデル・全6設定のC stamp完全一致、複素応答と既存SPD/独立MNAを確認したが、全forwardのRF応答系列は測定していない。連続周波数・EM・公差・実測等の認定でもない。詳細な時間差は、このhost・固定ケースに限る。
