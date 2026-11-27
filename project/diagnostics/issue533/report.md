# Issue #533: Stage 2 終点からの単発 TRF 精密化

## 条件・実行・証拠

- 最新 main `060a509be5ab6a4a980367783ab03ceeab27d1d0` を基点とした clean 実行 HEAD `3bd63003cd17b86316ceedff7657396236c615f0`、source SHA `e8c0ac44890267b866ed90d625a4ed70aa975215a74fd6d7311f9f2c7c4d6d34`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL 各1、plain、標準 CLI、lk指定（TRF実効off）。#529の実行 source の全ハッシュ・記録環境は今回と一致（HEADは異なる）。
- #529 固定 `0f7b1097217f913cfbaaf77b4fb1c0ddbad88bd3` の Stage 2 最終順位 2015, 2008, 2037, 2031, 2001, 2038, 2025, 2009 の25座標・vector SHAを照合。Stage 1・EXP-062参照vectorを開始点にしない。#529 Stage 2 Plan と RF profile・全格子・bounds は一致。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、4L2C definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。外部ポート、全6設定・28別区間、Search 70点（pass2/stop3）、Terminal 476点（各17）、独立MNA [0,111]、checkpoint 1000、GJM01最大10 pF・他は物理bounds。
- 8単一arm Plan、各8開始点、TRF signed_margin_db/sum、Search最大10,000/Job、restart無効。A1〜A4: x_scale=1、A5〜A8: jac；それぞれ ftol=1e-6、1e-8、1e-10、null の順。xtol/gtolはSciPy既定1e-8。nullはftolのみ無効。入力・SHA・Plan・ソース・環境は `inputs/` と `preflight.json` に凍結。
- 2026-11-27 13:43:10〜13:50:45 UTC に逐次実行。A1/A2/A5/A6はexit 0、A3/A4/A7/A8はexit 4（全Job照合済みだが各1件未収束）。異常exitなし・retryなし。実消費 **208,930 RF forwards**（Search 208,866 + Terminal 64）、**14,651,084 requested RF samples**、**128 MNA**；上限640,064 / 44,830,464 / 128内。条件別実消費とコマンド・時刻は `results.json`、CLIログはarchive。
- `audit.py` は全64件のPlan/入力/ソース/receipt/全rawバイトSHA、実消費、単一run、vectorとcheckpoint SHA、全6設定の部品制約・SPD・接続、Terminal格子の受動性・電力保存、指定2点の独立MNA・受動性・電力保存を照合。固定S2P SHAと全開始点物理/SPDは事前照合。チェック対象は有限格子と指定2点である。
- `results.json` SHA `c8b53b2cca5460f856d689791db64e4defc4cfb72c87caab298b9dcc86aab0b3`。全64件の初期/最終vector・SHA、#529開始Search J・改善量、Terminal J・max margin・IL/H2/H3、停止/status/success/optimality、nfev/njev/forward/wall、局所run・checkpoint、条件間seed別差・四分位・全座標の物理単位/正規化ばらつきを含む。`preflight.json` SHA `7d3843451196a9f1fed0e2201a6ccf1f84a86452f098d552cfc692d0137c1d23`。
- 全raw 472ファイルは `raw-cli-evidence.tar.gz`（PAX形式、SHA `5e4f3a6399c07e2bdb965828b645b5d3ceaade15f16e22828c0eb4471c046588`）に保存。元rawは `/tmp/issue533-run` に残置。archiveから別ディレクトリに展開し、下記の監査再実行で `results.json` とbyte一致を確認済み。空きディレクトリを用い、既存rawを上書きしない。

```sh
mkdir /tmp/issue533-example-replay
tar -C /tmp/issue533-example-replay -xzf project/diagnostics/issue533/raw-cli-evidence.tar.gz
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python project/diagnostics/issue533/audit.py /tmp/issue533-example-replay/issue533-run project/diagnostics/issue533/preflight.json /tmp/issue533-example-replay/results.json
cmp project/diagnostics/issue533/results.json /tmp/issue533-example-replay/results.json
```

#529保存Search Jを開始点の基準とし、今回の再評価は追加していない。SciPyの正規化・境界内移動による実際の最初の評価vectorと入力vectorの最大座標差は `2.998e-10`（単位は該当座標）、したがって開始Jの厳密な再計算一致は未確認。全件保存開始Jより改善。Search JとTerminal正違反二乗和は格子・尺度が異なる。

## 結果

| 条件 | ftol | scale | Search J 最良 / Q1 / 中央 / Q3 / 最大 | Terminal max margin 最良 / 中央 dB | Search forward 中央 | 終了内訳 |
|---|---:|---|---|---|---:|---|
| A1 | 1e-6 | 1 | .024640 / .027041 / .030813 / .038967 / .134341 | .082637 / .093535 | 43 | ftol 8 |
| A2 | 1e-8 | 1 | .021582 / .023767 / .024259 / .026031 / .111316 | .081353 / .084764 | 1,359 | xtol 7、ftol 1 |
| A3 | 1e-10 | 1 | .021582 / .023767 / .024259 / .026031 / .111307 | .081353 / .084764 | 1,359 | xtol 7、予算1 |
| A4 | null | 1 | .021582 / .023767 / .024259 / .026031 / .111307 | .081353 / .084764 | 1,359 | xtol 7、予算1 |
| A5 | 1e-6 | jac | .024556 / .026440 / .028185 / .039017 / .122545 | .082472 / .091067 | 200.5 | ftol 8 |
| A6 | 1e-8 | jac | .020955 / .021159 / .021361 / .021881 / .111307 | .080507 / .080958 | 5,192.5 | xtol 7、ftol 1 |
| A7 | 1e-10 | jac | .020955 / .021159 / .021361 / .021881 / .111210 | .080507 / .080958 | 5,503.5 | xtol 7、予算1 |
| A8 | null | jac | .020955 / .021159 / .021361 / .021881 / .111210 | .080507 / .080958 | 5,503.5 | xtol 7、予算1 |

全64候補はTerminal格子で性能feasibleではない。全runの局所bestと終了vectorは一致したが、一般には `optimality` は終了点指標であり最良点の勾配保証ではない。xtol成功は小さなstepによる停止であり、gtol達成や高精度最適性を意味しない。7件のxtol終了optimalityは例えば A2 で約0.00676〜0.03446、A6で約0.00966〜0.01682。A3/A4/A7/A8の予算終了は全てseed 2009。seed 2009はA6でもSearch J=.111307で他7候補の約.0210〜.0221より大きく、除外していない。

- **ftol効果:** 同一scaleで1e-6→1e-8は全8 seedでSearch J改善。対応差の中央値はscale=1で−0.006253、jacで−0.006986 dB²。中央値forwardは43→1,359、200.5→5,192.5と増加。さらに厳しくしても7/8は同一のxtol終了；2009は予算を使い小さなSearch J改善があるがTerminal最大marginが必ず改善するわけではない。
- **scale効果:** 同一ftolでjac−1のSearch J中央値差は1e-6で−0.000548（8件中6改善）、1e-8で−0.002232（8件全て改善）。ただし前述のforward増加があり、同一計算量での優劣を意味しない。1e-10/nullでも中央値差−0.002232、7件はxtol、2009は予算終了。
- A1最終Search Jへの到達は保存checkpointまたは局所run終了の観測からのみ上界を記録（`paired_vs_A1`）。例えばA2のseed 2037は1,000 forward以内、A5のseed 2001と2025は保存観測で未確認。checkpointは瞬間値であり未確認は未到達の証明ではない。開始時刻・局所wallとinput→receipt時間は計測範囲が異なる。
- 最良Search JはA6/7/8 seed 2031、.02095465。Terminal max margin .08050671 dB、正違反二乗和 .15797152 dB²、worst IL .83050671 dB、min H2 29.99889663 dB、min H3 29.99884278 dB。これは外部ポート有限格子のbest-foundであってRF適合ではない。
- 8候補間の素子ばらつきは精密化後も大きい。例 A6 は vector index 21（可変C）の範囲2.7689 pF、bounds幅の92.3%、index 1（L）の範囲18.4644 nH、幅の69.4%。全25座標・各条件のmin/median/max/rangeを保存。近いJでも同一解とは限らない。2009の異領域や他seed間の差は、局所解、悪条件、予算不足などの仮説と整合し得るが原因は未確定。

## 設定候補・限界

初期の広域探索・restart付きStage 2の優劣は今回の設計では評価していない。良好な終点からの**単発精密化候補**として、安価な停止はA1、精度重視はA2、より多いforwardを許す場合はA6を提示する。1e-10/nullは今回7件がxtolで同値、2009は予算終了なので、それ自体が追加の精度保証とはならない。標準設定変更・採否はユーザー判断。

連続周波数・高密度評価、SRF、Q(f)、EM、公差、実測・物理実装可能性、広域探索、全域最適性は未検証。試験条件の開発Runであり正式EXPではない。
