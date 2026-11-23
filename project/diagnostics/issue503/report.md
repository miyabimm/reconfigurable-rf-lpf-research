# Issue #503: TRF開発Runner接続の小規模確認

正式EXPではない。`plain.py` を 1 thread（OPENBLAS/OMP/MKL）で実行。再現例: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python project/diagnostics/issue503/plain.py /tmp/<fresh-path>`。初期状態は `issue470/config.json`, `starts.json`、seed 1013、4L2C・25変数。TRF単一run、最大3感度forward、Search 70点・Terminal 476点、Search MNA spot 1点／Terminal 2点、checkpoint間隔1。RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、固定S2P・bandsのSHAと完全な実行環境は `summary.json` に記録。

最終実装測定のsource HEAD `df6e9b4ff7f95c59b3e05788547343267cda619c`、dirty patch SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`、source identity SHA `b74e6511358cdab7261885f191aec50a07194364401257bd6680616d70ca0a23`、Plan SHA `66c60bcd55963e73abb8e88d4432766b3f8ff9435b6451ca08a1edf18df952c2`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、選択vector SHA `199a42a4d125a65651f2ff63dd8ddd5e16e00b38209dc2ccae26d31567c7e3c6`。詳細vector・検索結果はsummaryに含む。

- Search: 感度評価3回、210 requested/computed samples、SciPy nfev=3、njev=3。status 0、`evaluation_limit`、**未収束**。最良目的値 21245.689369087064 dB²。
- Runner全体: 4 forward（Search 3 + Terminal 1）、686 samples、独立MNA 5 samples。格子上のTerminal受動性・電力保存、指定独立MNA spotはpass。選択点のSearch指標確認のため、Runner予算外に別途 scalar 1 forward・70 samplesを実施。
- 選択点 Search／Terminal共通の今回有限格子値: 最大pass IL 8.3818331638 dB、最小H2/H3減衰 7.1993143970 dB、最大signed margin 22.8006856030 dB。性能条件を満たしていない。
- 単発plain時間: Runner wall 0.7754 s / CPU 0.6730 s、TRF内 wall 0.0528 s / CPU 0.0340 s。性能比較ではなく時間の再現保証もしない。

`summary-first.json` は先行測定（source HEAD `86cfba89`）で、後続のSciPy不正出力検査追加前の結果。選択点と上記指標は一致するが、最終実装の測定とは区別する。両runの一時rawは作業環境の `/tmp/issue503-plain-jqZpLs/run`、`/tmp/issue503-plain-final-DlFFSE/run` に保持（これらは正式実験原本ではない）。

有限格子の数値観測であり、TRF優位、連続帯域適合、全域独立MNA、Q(f)、SRF、EM、製造誤差、実測や物理実現性を主張しない。
