# Issue #513 比較前の凍結（RF-T010 trial）

校正・比較とも計算HEAD `0be67a193200f2065b1e36cb3e2dd231471cf77d`、単一ホスト逐次、OPENBLAS/OMP/MKL各1、既存develop Runner `timed`。校正seed 1013、Hybrid両条件nominal 15,000、TRF 5,000。校正結果の品質はN選択に使用しない。

- 校正Job wall: H0 3.497222957秒／15,002 Search forward、H1 3.522425171秒／15,002、T 22.900466873秒／5,000。各Job wallにTerminalと計測負荷を含む。Hybrid 2件の平均wall/forwardで外挿して約98,000、1,000単位に丸め **N=98,000**（上限140,000以下）。固定forward比較であり厳密な同一wall時刻比較ではない。
- 校正消費は別途 Search 35,004、総RF 35,007、requested samples 2,451,708、独立MNA 6。校正CLI exit 4（未収束）、3 Jobの科学・台帳監査PASS。最初の集計スクリプトはHybrid rawに存在しない `restart_count` を参照して失敗、rawは変更せず監査スクリプトを修正し再照合した。Jobの再実行はなし。
- 事前照合 RF forward 0、20初期vectorは#465・#511両方とSHA一致。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、RF-T008 base `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。固定S2P、6設定28区間、Search70/Terminal476、独立MNA `[0,111]`、checkpoint 1000を照合。
- 比較Plan SHA: `6f5d490dfa51d659284aec26e95a6eae90fd5ecc70eb2e48bc784d2096fea420`、`aaa88fe248435e9fb09e939e0b303c521a5e7b9a37d2cbc6204703ef32c5663b`、`820cddbd33bbb98e3659423257959bc5ff3ed9a24b2937690168f2320e639133`。それぞれseed 1001–1007、1008–1014、1015–1020、arm順 H0/H1/T、H1/T/H0、T/H0/H1。
- 各seedの3費目予約：総RF 201,051、requested samples 14,074,788、MNA 6。60 Job全体の予約：Search 4,020,960、総RF 4,021,020、requested samples 281,495,760、MNA 120。Hybrid各Job Search上限は開始済みFDグループを含む98,024、TRFは5,000。
- 校正原本 `/tmp/issue513-calibration-1795534383/`、比較の凍結入力 `/tmp/issue513-comparison-1795534383/`。system tmpは永続保存でない。正式EXPではない。
