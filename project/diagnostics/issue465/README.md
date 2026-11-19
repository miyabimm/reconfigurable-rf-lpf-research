# Issue #465: Hybrid 目的式 paired 開発 Run

## 結果（有限格子、正式 EXP ではない）

同一初期 vector の20対、476点 Terminal `J=max(e)` で、新目的式は旧比 **18改善・2悪化・0同値**。旧中央値 5.3209530691 dB、新中央値 4.0186879777 dB。旧最良 2.4206628356 dB（1018）、新最良 **0.7477583470 dB（1013）**。両群とも 0/20 PASS。新最良は EXP-062 A6 参照 J=0.07784114846285017 dB より +0.6699171985 dB 大きい。探索粗格子の solver objective は異なる関数なので比較していない。20対の Terminal J、IL、H2/H3、差、local_runs、停止理由、initial/final vector SHA、raw SHA、checkpoint数は [paired.csv](paired.csv) に記録。

全20 Job は予算100,000 Search forwardsに到達し、`evaluation_budget_exhausted`、数値未収束。Runner終了コード4は全Job照合完了・未収束ありを意味し異常STOPではない。収束とRF閾値は別判定。対象20 seedと有限予算に限定した観測であり、一般的優越性・大域最適性の証明ではない。

## 条件と入力照合

- 実行時 main HEAD `519215ad1670cb583a48ecf83d1e5c33414c7a80`、作業tree clean。旧 raw 内 HEAD `6ad2ea2a1d9f16b7493d3e311302e1a2b3414844`、clean。source identity SHA 旧 `72983e455b5d58a03e50f2a2fdf3b49914e62f7c01baa31b1a29e2b37bc08f42`、新 `fc5a58672f9e06e2ceea9122e3f8cd6622b34c29cc9ef03e2f07b371f3e33df9`。
- RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、RF-T008 rev3 base `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。definition canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。固定S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- 4L2C・25変数・6設定・28個別区間、外部port cascade、source 50+j0Ω、load 60−j40Ω。旧・新とも全物理bounds、Hybrid sum、sigma 0.1、70 Search samples、Terminal 17点/区間＝476 samples、MNA spot `[0,111]`、checkpoint間隔1000。Search MNAなし。
- 旧 Plan canonical SHA `dc477e77ed0633047345e04f450ccd2df84bfdd3ddbb0a3395bfed1a8d0e69dd` は Issue 指定と一致。旧 plan 原byte SHA `bb0cb38e1b8a8d890b9f99b6db00b1fa173e9fda0ebc37a7c20478a4b6b89928`。新 Plan canonical `b32f4d3e3314cf66eeff0b60c125114de2143d13806fa43560c386755f55eb7d`、原byte `1f1d88f15d7367cfe9feab1b5b001ee36ed625d54288345702f7a1982347dfa9`。SHAの種類を混同しない。
- 旧原本 `/tmp/issue461-stepA-uSS5rKDy/run/` を発見。20 Jobの入力・初期vector・SHAをPlanと照合、旧新Planのjob・格子・boundsが一致。開始前に全初期値の物理検査と全L行列SPD検査を通過（最小固有値 5.2043401573e-10 H）。旧20 Jobのreceipt・台帳記載の raw 2,078 ファイルを原byte照合。旧会話添付要約の原byte SHA `555d2b729d2c00af66f836be2f7fda518801f3538deb8b1ab686a160a4b7a67b`、20件のJ・IL・stop・local_runsを旧rawと照合し一致。
- 新config raw SHA `d95ba7e26f72ec5bfdf752ea22feb42fc1efbae86bcebae8401380525e1f2632`、starts raw SHA `81af6437a862ffac0bec61f4225b1420aa94377dbcfe14b98d3d499175208c61`。旧 run.json raw SHA `a75ba3be737f1cf9908b1b8ebe52b6f0bf88869d54e0790be0972c19e98a39a9`、新 `16d6fb7977b10d2469813c3eb2460205d260ef705983b12ba3900441fd7feb4d`。

## 検証・予算・再現

新旧とも全20件のrun台帳・receiptに記された全rawファイルのサイズとSHAを再照合。Terminalの物理条件・全L SPD・外部受動性・電力保存は記録上20/20 pass、独立MNAは各2点で20/20 pass。これは連続帯域の独立検証ではない。新checkpoint計2019件、旧2018件。新 Run の予約／実消費は RF forwards **2,000,020**（うちSearch 2,000,000、Terminal 20）、requested RF samples **140,009,520**、独立MNA **40**。全費目の未消費解放0・不明0。旧rawにも同数の実消費が記録され、旧新のSearch forward差は0。旧実行wallの測定記録は未確認でwall費用差は不明。

新実行wall 1330.04秒（`/usr/bin/time`、Run全体；Job別wallは記録なし）。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL threads各1。新 raw・receipt・checkpointsと実行ログは `/tmp/issue465-paired-55K6P49j/` に保持（system tmp、永続保管保証なし）。旧証拠も上記tmpに保持。どちらも削除していない。

集計再実行（RF forwardなし）:

```sh
python3 project/diagnostics/issue465/analyze.py /tmp/issue461-stepA-uSS5rKDy/run /tmp/issue465-paired-55K6P49j/run project/diagnostics/issue465/paired.csv
```

Dense格子、連続周波数適合、SRF、Q(f)、EM、製造公差、実測・物理実装可能性は未検証。追加探索・正式EXP・Step B/Cは未実施。独立レビュー待ち。
