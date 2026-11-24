# Issue #513 — Hybrid ftolとTRF restartの時間近似paired比較

## 結果（RF-T010 trial、正式EXPではない）

20 seed × 3 arm、同一seed初期25変数、外部port Terminal 476点の `J=max(signed margin)`（小さいほどよい）。全60 Jobは予算終了・数値未収束、有限格子PASSは各0/20。

| arm | 条件 | J中央値 / 平均 | 最良 / 最悪 | Job wall中央値 / 平均 (秒) | 範囲 (秒) |
|---|---|---:|---:|---:|---:|
| H0 | Hybrid、ftol省略 | 4.018688 / 4.088820 | 0.767839 / 8.837096 | 21.576 / 22.384 | 20.422–29.196 |
| H1 | Hybrid、ftol 1e-7 | 3.278472 / 3.086886 | 1.399508 / 4.614058 | 21.802 / 22.241 | 20.494–24.486 |
| T | TRF、ftol 1e-6 | 0.675567 / 2.624226 | 0.105919 / 11.867147 | 25.069 / 26.479 | 22.750–33.018 |

| paired差（前者−後者） | 改善 / 悪化 / 同値 | ΔJ中央値 / 平均 | 最小 / 最大 |
|---|---:|---:|---:|
| H1−H0 | 13 / 7 / 0 | -0.845783 / -1.001934 | -5.672266 / 2.618142 |
| T−H1 | 14 / 6 / 0 | -1.764868 / -0.462661 | -4.285740 / 9.249225 |
| T−H0（参考） | 15 / 5 / 0 | -3.015991 / -1.464594 | -6.679029 / 7.775404 |

この有限比較ではH1はH0より中央値・最悪値が良いが、個別には7 seedで悪化し、最良単一解はH0。TはH1より中央値が良く14勝だが、最悪値は大きく、6 seedでは悪化。T/H1のJob wallは中央値で約15.0%、平均で約19.1% Tが長い。T対H1は解析Jacobian/cache等も異なる**現行経路全体**の時間近似比較で、ftol単独の効果でも厳密な同一wall時点比較でもない。#511 Cの履歴値は代用せず、Tを今回20 Job実行した。

H0/H1/TのSearch目的中央値は99.715330/77.005929/3.195520 dB²。Terminal worst IL中央値は3.481724/2.838986/1.425567 dB、min H2中央値は26.999277/28.149904/29.928805 dB、min H3中央値は26.959807/27.404677/29.965890 dB。各全局所run数は73/107/267、restart数は53/87/247。H0/H1のL-BFGS-B局所終了はftol相当52/86、projected gradient各1、予算中断各20。Tはftol終了247、評価上限20。局所成功と全体未収束は別。全局所終了詳細・時間・選択vector・初期vector・SHA・Job別費用は `summary.json`、paired数値は `paired.csv`。

## 固定条件と費用

- 実行HEAD `0be67a193200f2065b1e36cb3e2dd231471cf77d`、source identity SHA `0791a2b013eb4a915a277590bd318a1abc3d72000a475af78588d60937a8f1e6`、source dirty patch SHAは空patch。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P input/output SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- 4L2C、物理box、6設定・28独立区間、外部S2P cascade、unit weights・sum squared positive violation、Search 70/Terminal 476、MNA terminal `[0,111]`、checkpoint 1000。Hybrid batch/partial FD true、lk cache、nominal 98,000・開始済FD完了を許容；TRF解析Jacobian、cache off、5,000厳密上限、x_scale 1.0。共にrestart_sigma 0.1。その他既定値不変。
- `freeze.md` に校正・N決定・全Plan SHA・事前予約を実行前に記録。事前照合RF forward 0、全20初期SHAは#465/#511に一致。校正は別費用：Search 35,004、総RF 35,007、samples 2,451,708、MNA 6。
- 本比較実消費：Search **4,020,800**、総RF **4,020,860**、requested samples **281,484,560**、独立MNA **120**。予約に対してRF 160・samples 11,200を解放、未知0。旧#511の消費とは別。3 Runの実行wall 482.84 / 495.72 / 449.79秒、user CPU 452.44 / 462.42 / 402.24秒、system CPU 16.98 / 16.99 / 8.37秒。CLI各exit 4は予算終了の未収束。Job CPUは未計測で局所CPUやRun CPUと混同しない。
- 同一ホスト逐次、AMD Ryzen 7 PRO 4750G / WSL2、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各1 thread。Job wallは `timed` の負荷を含みplainとの差は未校正。Run開始/終了時のloadと完全な環境は `summary.json`。校正はseed 1013のみであり、TRFの他seedへのwall予測誤差を含む。

## 監査と限界

各Run終了時にPlan・台帳・receipt・checkpoint原byte SHA、予約/消費/解放、選択vector、box/SPD、Terminal全格子の外部受動性・電力保存、独立MNA 2点を監査。後に選択vector・全checkpoint vector SHA・最終checkpoint・solver optionsとの一致を追加して60 Jobを再監査、最初のcompact抽出と一致。全60件科学監査PASS、最小L固有値 3.9437e-10 H。監査PASSは閾値適合を意味しない。計測・結果rawは `/tmp/issue513-comparison-1795534383/`、校正rawは `/tmp/issue513-calibration-1795534383/` に保持、Git非管理かつ再起動後の保存は保証しない。

有限格子での観測であり連続周波数、SRF、Q(f)、EM、公差、測定、実装可能性、全域最適は未保証。検索予算やftol既定、RF仕様の変更、追加sweep、正式EXPは実施していない。

## ソフトウェア検証の注意

Issue固有・Hybrid・batch/partial FD・TRF・Runner・timingの対象回帰と正式EXP storage auditはPASS。一方、任意の全ファイル `unittest discover` は514件中19 errorで失敗：mainから変更のない旧RF-F001/T001/T002を参照するテストと、既に撤去された `lpf.port_parasitics` を必要とする旧EXPテスト。CIのselectorは旧数値replayをroutine FULLから除外するが、これらを全テストPASSとは扱わない。詳細ログは上記comparison tmpの `unittest-full.log`。
