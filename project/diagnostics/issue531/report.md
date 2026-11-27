# Issue #531: TRF restart の対比較

## 実行条件・証拠

- A = main `303d6dcf6328f4dd19199a20515d11ef4bd94237`（直前の局所終了点）、B = `6fcff76b22e576b10088c7c5086e10b277307abd`（同一 TRF 呼出の累積最良点）。実行前の source identity の `files` は `src/lpf/optimizers/trf.py` のみ異なり、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、3 thread 環境変数=1 は一致。両 tree clean。両者の標準 CLI、plain、`--rf-cache-mode lk`（TRF 実効 off）。
- RF-T010 trial、effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`。4L2C、同一 bounds（GJM01 10 pF 上限）、全6設定・28区間、外部ポート。Search 70点、Terminal 476点、MNA indices [0,111]。Plan SHA `0ec3bfbec3c6e47ddb88aa5e59c278d287b705cb16590c3490d45f79da997a6f` は両者で完全一致。
- #529 固定 commit `0f7b1097217f913cfbaaf77b4fb1c0ddbad88bd3` の Stage 1 上位8候補の vector・SHA を Stage 2 starts と一致確認し共通利用。EXP-062 reference vector は不使用。入力・元ファイル SHA と選抜は `inputs/manifest.json`。
- 1 Job Search 20,000、TRF `signed_margin_db/sum`、ftol=1e-6、x_scale=1、sigma=0.1、checkpoint 1000。両版の予約・実消費は各 160,008 RF forward（Search 160,000 + Terminal 8）、11,203,808 samples、16独立MNA。計 320,016 forward、22,407,616 samples、32独立MNA。16件全て budget exhausted、数値未収束。標準 CLI は両版 exit 4（全 Job 照合済、未収束あり）で異常 STOP ではない。A 20:58:52〜21:04:16、B 21:04:16〜21:09:40、各約324秒（2026-11-27 +09:00）。
- `preflight-{a,b}.json`、入力、`results.json`、`execution/`、`audit.py` と `raw-cli-evidence.tar.gz` を保存。archive SHA-256 `350476dc03d998e9f55053b28097e292995101f104943a0dfb61e112cbe52ae7`；388 raw files を圧縮前バイトと照合。元 raw は `/tmp/issue531-raw-{a,b}` に残す。archive を `/tmp` に展開すれば `audit.py` で再照合可能（既存 raw を上書きしないこと）。

## Terminal 結果（A → B）

`max margin` は小さいほど良い。`J` は Terminal の正違反二乗和 dB²。IL は最大、H2/H3 は最小の外部ポート減衰 dB。

| seed | max margin dB | J dB² | worst IL dB | min H2 dB | min H3 dB | restart A/B |
|---:|---:|---:|---:|---:|---:|---:|
| 2008 | 0.301786 → 0.294818 | 3.672844 → 3.316243 | 1.051786 → 1.044818 | 29.993772 → 29.992528 | 29.985290 → 29.991415 | 23/33 |
| 2009 | 0.151548 → 0.297375 | 1.468515 → 3.241029 | 0.901548 → 1.047375 | 29.991162 → 29.993563 | 29.997511 → 29.988899 | 31/32 |
| 2031 | 0.302260 → 0.296029 | 3.425886 → 3.437990 | 1.052260 → 1.046029 | 29.993582 → 29.991661 | 29.989925 → 29.990337 | 26/29 |
| 2015 | 0.265233 → 0.298058 | 3.637777 → 3.727174 | 1.015233 → 1.048058 | 29.985194 → 29.991899 | 29.989703 → 29.987038 | 31/24 |
| 2025 | 0.100650 → 0.299045 | 0.346138 → 3.331077 | 0.850650 → 1.049045 | 29.998487 → 29.993458 | 29.997742 → 29.988159 | 26/28 |
| 2038 | 0.304331 → 0.296243 | 3.571732 → 3.354611 | 1.054331 → 1.046243 | 29.992550 → 29.992415 | 29.991258 → 29.991008 | 39/33 |
| 2001 | 0.095788 → 0.125895 | 0.297929 → 0.664006 | 0.845788 → 0.875895 | 29.999224 → 29.996657 | 29.997351 → 29.998689 | 29/9 |
| 2037 | 0.297501 → 0.298118 | 3.422383 → 3.377540 | 1.047501 → 1.048118 | 29.992591 → 29.992592 | 29.990819 → 29.988452 | 35/38 |

最大 margin は改善3、悪化5、同値0。Jも改善3、悪化5（内訳は異なる）。最大 margin の最良値 A 0.095788 / B 0.125895、中央値 A 0.281367 / B 0.296809 dB。J の最良値 A 0.297929 / B 0.664006、中央値 A 3.424134 / B 3.342844 dB²。全16候補ともこの Terminal 格子で性能 feasible ではない。全メトリクスの seed 別差と最小値・中央値は `results.json`。

Search 目的値は `results.json` に全件記載。観測された 0.05 以下への到達 forward 上界は A seed 2025: 9000、2001: 14672 のみ。0.03 以下は両版とも保存観測では見つからない（未到達の証明ではない）。周期 checkpoint はその時点の観測であり累積bestではない。局所run終了時の局所best・累積best・forward・optimality は `local_observations`、全局所run原記録と checkpoint は archive。時刻ベース Job 時間と局所run wall 合計も保存し、計時方式の違いに注意。

## 監査と限界

`audit.py` は全16 Job の Plan/input/source、台帳・receipt と全 raw の byte SHA、予約と実消費、全局所run の seed/RNG/clip からの restart start vector を照合（B は各時点の累積最良、同値先着）。最終 vector と SHA、全6設定の部品制約・SPD・接続、Terminal 格子上の受動性・電力保存、指定2点の独立MNA・受動性・電力保存を照合した。固定 S2P SHA と開始点の物理/SPD は事前照合。高密度評価は未実施。

これは選抜済み8初期値・20,000予算に条件づけられた有限探索であり、広域探索、85,000予算、連続周波数での優劣を示さない。シミュレーションだけでは SRF・Q(f)・EM・公差・実測または物理実装可能性を保証しない。結果は混在し、科学的採否はユーザー判断。正式EXPではない。
