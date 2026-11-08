# Issue #343 — 非現役の履歴資料

このREADMEは元パス・blob・検証上の注意を示す読み取り専用の履歴索引。
Issue #362で旧Pythonコピー40件は現行treeから削除した。以下の「隔離」「保存」や
「コピー」は当時の処置を記すもので、現行treeにPythonファイルがある意味ではない。
各節の元commitと元パスを使い `git show <元commit>:<元パス>` で取得する。
Git objectが必要であり、旧コードは**現役APIではない**。実行には対応する
実験記録・条件・依存環境を確認する。履歴の取得だけでは再現PASSにならない。
元EXP/historyおよび過去のsource fingerprintは変更しない。

元main: `681dabee30a7804d63bacc3afa5932e320c1d11a`。
以下は内容バイト不変の移動であり、SHA-256はファイル内容、blobはGit blob ID。

|元パス|元blob|内容SHA-256|保存理由と対象|
|---|---|---|---|
|`src/lpf/phase2_models/experiment_config.py`|`4b2a02ab46ae272a8b4326e48598ecdee3f04669`|`964a9405ee2296fd3ff8814f89f29d36c87efac4bf3681cf335544a74a8a4768`|旧schema4/5 continuation計画、EXP-116 nominal input参照、固定SHAと準備方式の解釈。schema2と同値ではない。|
|`scripts/prepare_issue250_comparison.py`|`cd2a7391eabb16f1bb0035d2a706aac1e522e660`|`164d7566d943b029b28dd6e78822e98dc74b31ed1ab22207d3c5c121a4c28e35`|Issue #250のEXP-062参照・比較start準備の歴史的意味。|
|`scripts/diagnose_phase2_scaling.py`|`a7c5d2e200009917f98cf26bccbd1258e9d0fdf0`|`6d18d6126dad8268942ecbb2a5a5f5ff47e2c539c05f6fe65408edd8efdef194`|Issue #235のEXP-086〜094の保存初期値、seed replayと有限差分尺度診断。旧RF条件に依存し、現役schema2とは同義でない。|

これらは旧RF-T008 effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4` に関係する。現行条件とは異なり、再評価・現行RF合格として読み替えない。元ファイルを読む例（Gitのobjectが存在する場合）:

```sh
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:src/lpf/phase2_models/experiment_config.py
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:scripts/prepare_issue250_comparison.py
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:scripts/diagnose_phase2_scaling.py
```

旧source固定の歴史integrationや実EXP再現はこの移設では実行しない。

## D3：旧post-searchの歴史的手法

元main `0698a87925b30ccaf11531a5197a5dc611d3f681` からバイト不変で移動。
17点・独立84点・dense等の旧検証段階、候補証拠の再計算・source結合は
現役G3/G4の保存検査とは同義でない。以下は直接importや実行を保証しない。
旧条件・対象EXPの正確な対応は元manifestと元commitで確認する。完全証拠checkoutでの
履歴再現は未実施。旧RF-T008の例は上記旧effective SHAであり現行条件に読み替えない。

|元パス|元blob|内容SHA-256|保存理由|
|---|---|---|---|
|`src/lpf/phase2_models/post_search_evidence.py`|`64c8fed2f1d7952c30eb2542c80aab8af8643cb5`|`c8a7a42eb7a36d1848c5d5ec99681b3df741cf8fca5032eeee28601a57c631ff`|旧候補の証拠形式と検証意味。|
|`src/lpf/phase2_models/post_search_validation.py`|`88ac720d8ea41bb59e8958d654b79bc3e27a9a51`|`b9e3939bfb60777595dd985b8998b834db22b897f6208aa7706a3e4130c6e1e2`|旧17/84/dense検証手順と段階分類。|

`git show 0698a87925b30ccaf11531a5197a5dc611d3f681:src/lpf/phase2_models/post_search_validation.py` で元sourceを参照できる。

### D3：独立scan・候補識別の非同値な旧手法

同じ元mainから以下もバイト不変で隔離した。旧`candidate_audit`と旧topology列挙は
削除し、現役への互換shimは設けない。

|元パス|元blob|内容SHA-256|保存理由・対象|
|---|---|---|---|
|`src/lpf/phase2_models/independent_scan.py`|`c70dac32446ab4af877b65a68dfe10afe8b3e973`|`5aaa89a01dfc22dd6459151833b5a889309b55a41424ef3f682eb2cc2b5e9ed8`|`minimize_scalar`による個別区間内spot極値探索。現役固定格子MNAと非同値。|
|`src/lpf/phase2_models/limited_candidate_evidence.py`|`665ed07056d2dc991e18ed70d789ebcfeba31aa3`|`58948d71c6688c91e769d93e8daf5ac1392accf5d8a4e5965abf785cb5d7a2c8`|旧candidateのdefinition/vector、環境・source・input結合と再計算証拠形式。現役raw形式とは異なる。|
|`src/lpf/phase2_models/problem_seed.py`|`de22f5e722927c76f9a292eff4a92801154dc44a`|`e2d338b26f2a1c14fb30975bc4f17aca87138c18c9f3dcbd44e6a34b21632d75`|旧definition/vector fingerprint・seed/epigraph座標の意味。現役Job seedとの互換は不要。|
|`tests/test_phase2_independent_rf.py`|`b8302e9cf632afa46e8b3308759950f3bf45a65b`|`4bb5017f92c39170a02d099e1e07737bb137677f87003fe10fbc3a6d72c918bb`|旧scanの極値・失敗oracleとEXP-042/043/055/058の固定vector参照・回路定義。現役CIからは実行しない。|

旧scan/evidenceは特定EXPに固定した実行器ではなく、渡されたpolicy/回路を使用する。
上記歴史testはRF-T005/T007/T008と保存EXP vectorを組み合わせているが、保存時の
旧RF effective SHA／source／環境による実EXP再現を認定するtestではない。
#307移行後のD1固定期待値の5条件回帰とは入力・条件・検証法が異なる。
対応する歴史RF SHAは`rf/constraints/history/issue307-migration.json`、実EXPの条件は
元manifestを参照し、現在の同名RF IDを過去のeffective SHAと同一視しない。

各元パスは上記と同様に`git show <元main>:<元パス>`で復元できる。
ここに移したtestは削除済み旧API/test fixtureも参照するため、コピー単体を現役
Python pathへ追加して実行しない。必要なら**元commitの環境全体**で再現する。
完全研究証拠の監査、保存EXP vectorの再実行、区間内極値探索・denseの再実行は未実施。
現役への置換範囲と未代替の差は[整理記録](../../project/diagnostics/issue343_d3_cleanup.md)を参照。

### D3レビュー補足：保存EXP固定テストの検証レシピ

以下2件も一般的な旧runnerテストではなく、凍結EXP入力と旧評価・識別手法を結ぶ
固有の再現レシピとして隔離する。元mainは
`a86f47b6bf6fe3b722195167c88a6fbb07e220d6`。内容バイト不変で、通常`tests/`や
現役CIへは戻さない。D1固定期待値は現行RF条件・別vectorであり、同値代替ではない。

|元パス|元blob|内容SHA-256|保存理由・対象|
|---|---|---|---|
|`tests/test_phase2_problem_frozen.py`|`d67fa28d48b4709135730ff4174746f6b4c19a00`|`b7cd38d123cc360d33817229004e4e8ad6498fc82e683b034bc2385ebf4ef2a6`|EXP-042/055/058の入力ファイルSHA・回路定義、旧`SampledEpigraph.seed`の完全vector・encode/decode・28/56点残差照合。全証拠checkoutを要するread-only opt-in手順。|
|`tests/test_phase2_candidate_records_frozen.py`|`7ff0eebb11bc4f33f4f4cd71b9b1ed0038c96f52`|`040addffd6b5ae2dd59dfb9ed642cd23eb6dafd84458728cc4e2cbb6ff57a5f7`|同EXP入力SHA、旧candidate roundtrip/再計算、`passed_limited`と`not_run`、限定MNA・電力残差、証拠深度の異なる候補を混同しない検証。synthetic callbackは歴史solver収束ではない。|

入力参照はEXP-042 `preliminary_js_5pt.json`、EXP-055
`checkpoints/cv1_input_tip_best.json`、EXP-058のarea4p667 snapshot、
problem testではarea3〜3p667 snapshotも含む。ファイル内の凍結入力SHAと
`831e9e56754e81d69b583893181c350396acc8f5`への参照をそのまま保存した。
これらの入力SHAはRF effective SHAではない。旧RF条件との関係は以下のとおり
（#307移行表の旧effective SHA、現行の同名IDとは非同値）:

|旧trial ID|#307移行前effective SHA|
|---|---|
|RF-T005|`59a451775ab4914cf9f0e51785ebfb62b36217af7735e7c93e9fe70f2323e67c`|
|RF-T007|`c6f0fc685464964fff2abedf8b99dda0064c99bbe133ec8fecd91c4f60d2b430`|
|RF-T008|`7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`|

保存したtest自体はRF effective SHAを固定せず、実行checkoutの`load_constraint`を
使用する。元mainは#307移行後なので、そこからコードを復元するだけで歴史EXPと
同じRF条件の再実行になるとは限らない。旧条件の正本・新旧SHA対応は
`rf/constraints/history/issue307-migration.json`、実EXPの条件/source/環境は
元manifestで照合する。現行条件でのPASSやsynthetic収束を過去EXPの認定に読み替えない。

元コードの読み出し（Git objectが存在する場合）:

```sh
git show a86f47b6bf6fe3b722195167c88a6fbb07e220d6:tests/test_phase2_problem_frozen.py
git show a86f47b6bf6fe3b722195167c88a6fbb07e220d6:tests/test_phase2_candidate_records_frozen.py
```

旧API依存も必要なので、再現する場合は元Git commitのcheckoutと全証拠・対応環境を
揃える。archiveコピーを現役Python pathへ追加して直接実行しない。今回確認したのは
元blob/内容SHAの一致と現役回帰のみ。旧solver・歴史EXP固定テストの実行、
完全研究証拠監査は未実施であり、この保存を実EXP再現PASSとは扱わない。

## D4：旧ABCD evaluator・EXPモデルとテスト資料

元main `d3616b8b832c9f44fe7811d459d59664e3db8a0b`。以下はすべて元パスの
バイト不変コピー（移動または編集前のコピー）であり、Git blobとSHA-256を照合。
現役Python path・CIに追加しない。元commitは#307移行後であり、元EXPの実行条件や
旧effective SHAに自動的に一致しない。旧T005/T007/T008のSHAは上表、実EXPは
元manifestを参照する。各行は`git show d3616b8b832c9f44fe7811d459d59664e3db8a0b:<元パス>`で読める。

|元パス|元blob|内容SHA-256|保存理由|
|---|---|---|---|
|`src/lpf/phase2_models/_grid.py`|`79c27a7f326bbf5ef3c2ab9abf50054f7157e900`|`a6e721a9b10360e2f7169a6e7feaf8fcf259a8823a45fa4b163637a49f232927`|旧3L格子とABCD外部寄生配列の生成、extra周波数。|
|`src/lpf/phase2_models/coupled_lc_evaluator.py`|`733612fc2d469f68353226f7bdf04263a3888261`|`9f9ef956230dbef1cbb9109e39f34d7a4657c71f73a3c97be186a986c560835a`|旧ABCD sampled forward。現役power-wave Sとは同じ実装でも独立MNAでもない。|
|`src/lpf/phase2_models/exp042.py`|`702ef2c8723c449ac9a832c44a898c14f5518e5a`|`7e28dc6ff042f692f94bf5f5c279c124cef1c9b4854f0ee6f0a14e4582d0fbc4`|EXP-042固有の構成と評価方式。|
|`src/lpf/phase2_models/exp055.py`|`507c341534adf62af776e9c7de330e7cc761762d`|`1c6eaf3fbef1bedb1d49b1f10cda7111237cbc3e78cf1d9c9a48002db6f88cc0`|EXP-055の構成、T007固定寄生、旧独立検証。|
|`src/lpf/phase2_models/exp058_area3.py`|`02b14057e0995c57a1e7ccf8da3fb5680a36a9f4`|`720d4a6189a6fc51d60f2249fba9f5f51638b083e0f34f0fe4d226ad970aced8`|EXP-058 3L構成・独立検証。|
|`src/lpf/phase2_models/exp058_area4.py`|`8bac346201ede3eb6bddb7e260668dd934a12268`|`c29dc8bfae8b34cb3ba99788f552af86b6f2126bf7889afd541ab529798d26fb`|EXP-058 4L構成・独立検証。|
|`src/lpf/phase2_models/exp058_area4l_gjm.py`|`d13ed0caf6aca4e55946a81e90b6873493723ba4`|`9582e4f42863f6076e64be8c916d1a10107de78b6d3de3cf6428aad33a0972c9`|EXP-058 4L+GJM構成・独立検証。|
|`tests/test_phase2_branch_mna.py`|`701e69fc4609a4ccb32f4926fbd47b0fa3b6702f`|`1d9666b03077e3e4afe531a23a13b01d32c85505da4a3a5fc5c8d54f46003ce8`|移行前独立MNAアサーション。|
|`tests/test_phase2_circuit_layout.py`|`402d4ac1c47a016a5f59f379e0bde9b740fb18e1`|`fcd130ecc9ce60ddaf83c5b7ad9f57f7d7bdc7428bc778a592a8d744bf035238`|EXP-055/058固定vectorの旧構造注入。|
|`tests/test_phase2_connection_roles.py`|`f44d4689979d527f888ed4bbbe6909d2895ac1ba`|`4823116b625d9cb52b7812509f38788cb1dc4436306fb30fda4a55e0797be62a`|旧role昇格報告とEXP-055固定vector。|
|`tests/test_phase2_numeric_diagnostics.py`|`2c1206cc6cc1c6be5745068dbb2c1d82d6c73c6c`|`65720e4eb3554d048b7044a6beca4f3ac3a4303ccb7455bf2e3c9c16f879349e`|旧ABCD固有のSchur/transferエラー。|
|`tests/test_phase2_rft008_layout.py`|`abca72407eb7cd6a9a18b24e449c4605fdc13cb8`|`b16e485500defb1ca74649a014fac52f0b58de24c2dac7fa58c471e8e3e08d4c`|EXP-058固定vectorの旧C配置とMNA。|
|`tests/test_phase2_s2p_grid_cache.py`|`9229f4f99e7962249347f3f9ab73b85d9485cb81`|`17cbe5c1d698473debcb717970f52d36c13f19a04fa5a6981efb2cfc3d85018c`|旧MHz格子hashとABCD cache。現役Hz格子と異なる。|
|`tests/test_phase2_generic_exp043.py`|`1e5a643a73c59d6f3e4db3abb63293d207428b6e`|`1ea5ea6e30b80d82d10ac11a97b8835babd06af090dddd831f7848cdeaf20df6`|EXP-043固定vectorと保存source比較。|
|`tests/test_phase2_public_circuit_api.py`|`747f263bb5346d7b8f66d62defc8b3fdbf7eea20`|`692522fb38a1c636f1b3c91874b0aa4ba2f1f938192933659de26dda603ca5cd`|EXP-042/055/058旧wrapper入力と出力。|
|`tests/test_phase2_rft005_t007_policy_circuit.py`|`c22768ebb02f663a1c3a400ad99034556f9afac1`|`c9f1c0f4bb717acabc71efbadc499225c81ff85c8f68451dbbacbd9b19d6fd9f`|EXP-042/055旧試験条件wrapper。|
|`tests/test_phase2_rft008_policy_circuit.py`|`716daa7947e98093efbb1bd2e7a8e719749da2bd`|`4c2c7c0c390e513313e3ed3e976a440a2e9ca9c652842dc7af59f79ef482dc95`|EXP-058旧試験条件wrapperと候補。|
|`tests/test_phase2_shared_exp_evaluators.py`|`99692cdab076597fe6767262c6c557907606109c`|`b989c37633852be823161fd6f907525188cf2c2f6da1477b376527b2c32ddd9b`|EXP-042/055/058旧sourceと共通評価器の比較。|
|`tests/test_phase2_zero_branch_projection.py`|`35bca64ea619cf69cb9e9320684dfa00de66ee11`|`351d1f8ebdaa7bf500ab93e0cbc4de61603decda8d0f8b2a1d46827ff8036591`|EXP-055/058旧zero-placeholder投影、現役searchに移植しない。|

現役検査への対応と残存旧layoutの理由は
[`project/diagnostics/issue343_d4_cleanup.md`](../../project/diagnostics/issue343_d4_cleanup.md)。
元EXPの再実行・旧ABCD固有エラー・旧格子hashの現役意味への同値変換は未実施。


## E2：旧matching layoutと履歴検査

元main `f5141a12f2600e6332cb6a9ba528dd2995879192`。以下は元パスと同じ
相対パスのバイト不変資料であり、旧facade・依存環境を含む実行可能パッケージではない。
`experiments/matching_limit/`の元sourceは変更していないが、現checkoutでは旧facadeの
root importが解決しない。旧runner・検査の実行が必要なら当時の完全なcommit/条件/環境を
取得する。単にarchiveをPython pathへ追加してはいけない。

|元パス|元blob|内容SHA-256|保存理由|
|---|---|---|---|
|`src/lpf/variable_c_layouts.py`|`2c08695738c08477d8b4361a68d3952917cae399`|`3d2f3c1749a9a666a65ed1ab7e2d01b94afcf18ba57a4f0c378587c47aa3e541`|旧bounded二段階列挙とlegacy部品alphabet。現役構造列挙と非同値。|
|`src/lpf/coupling_layout.py`|`611c3826f21c872868ef4759a4f37f6c1e1f0ff9`|`76be428de62feced1b8a0a6d0a4820762bad7265b6fdcaf7d9a280d508c75683`|旧物理隣接・nominal/感度結合とSPD検査。現役合法性と非同値。|
|`tests/test_search_space_extensions.py`|`6017fdbd5c09591d14a813f127d07fb2be3e589e`|`17b949772a5e1cb583957b5f768ce5b8338fb875db08f5a3c1df2580982b75c2`|旧matching設定・3形式比較と現役bounds混在の元検査。|
|`tests/test_grounded_enumeration.py`|`bb8fa98bd54cd227b2a9beb6f645149d19e9547f`|`8cc7aa8d039d9226865ce7f558dddec142f70a17291add264f84f6922e609f29`|旧ground graph列挙・budget検査とMNA混在。|
|`tests/test_node_area_selection.py`|`4b26c4574c3c229f4c8904527b9dd2d74ab25cd3`|`cf74a8197ddb539c13c9b4e150376936f745b942cfe14968151fa88c1035bfdd`|旧samplerの15セル選別とinvalid budget。|
|`tests/test_coverage_sampler.py`|`23fefd5a24714ab2b45d605dea8160338d009581`|`eb5fefd082ea887e8a9a5cb6ec1f40f2f7ab112bc78f8a448b3b3befeaaba19a`|旧samplerのseedと構造・coverage契約。|
|`tests/test_p4_resume_integration.py`|`1bf3eab0e0350e7b325dd44d7ffbbdbb0bc5dead`|`7cb1effc4884cc4255e7b7ad15d88d5e7bc9e6599b6f91f3baeb0184c137c3c2`|旧P4-A中断・resumeとcheckpoint動作。現役Campaignとは別契約。|
|`tests/test_full_lpf.py`|`e734a6b3b9ce13b29fdf1431056d73f283dbb2e4`|`1e40a83487cf298f7dc2cf3b1447da049558764de4f5a4a79842349b369b43b9`|旧RF-F002 full_lpf目的関数・最適化検査。|
|`tests/test_full_lpf_checkpoint_import.py`|`d8ea8ecb91288b20a664de06b372ca45f3ceb438`|`8c62deefc869f9613bda47c3856c60ca12d498912d9a3b727fbd79936294fb30`|EXP-017/023旧checkpoint端子変換と固定数値の検証レシピ。|
|`tests/test_rf_f002_search.py`|`f95d68bd7dbfca786bd96da905c59325e79edc9d`|`46704347a3fd52df92392db7e27805a01d28e6f6638aa0d779a69a4340799290`|旧RF-F002/T004設定構築・bounds。E1では既にloader拒否によりskip。|

旧RF-F001/F002/T004のeffective SHAは、それぞれ
`df6b4cbd347aac06538527cd68963b785207582152e17117a683c10058af0c54`、
`f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`、
`c66302a281a1fdb88da355fc44dac1ef3b1c4e18e8ff297db9e842b219b5b0c4`
（`rf/constraints/history/pre-issue-307/provenance.json`）。個々の試験・EXPは
自身のmanifest・source・条件で照合し、同名IDや現行trialと混同しない。元mainは
#307移行後なので、そのcheckoutだけで歴史条件の完全再現にはならない。

例: `git show f5141a12f2600e6332cb6a9ba528dd2995879192:src/lpf/coupling_layout.py`。
全10件のblob一致を確認したが、旧matching runner・旧EXP・denseは再実行していない。
現役テストとの対応と非同値な喪失範囲は
[`project/diagnostics/issue343_e2_cleanup.md`](../../project/diagnostics/issue343_e2_cleanup.md)を参照。
