# Issue #319 — Stage 4C-2 開発用親Runner

## 境界

`lpf.search.runner.run_development()` は schema 2 の **開発専用・system tmp・同一プロセス逐次** API。
正式CLI、EXP、G0/G1、G2–G5、Scheduler、並列、retry/resumeは接続しない。
既存 `run(..., mode='fixture')` / `execute_job()`、RF core、solver、Workerは変更しない。
RF-F003の正式条件を使うソフトウェア検証であり、正式実験・RF仕様適合の認定ではない。

```python
from lpf.search.runner import run_development
from lpf.search.storage import vector_sha

# plan = load_preflight(...): definition参照付きschema 2、既に検査した入力
# definition/policy: 同じPlanの完全回路定義/条件
# x_by_seed: 呼出側が全seedに明示指定した合法な完全physical vector
starts = {seed: {'vector': x.tolist(), 'vector_sha256': vector_sha(x)}
          for seed, x in x_by_seed.items()}
state = run_development(plan, definition, policy, starts, fresh_system_tmp_path)
```

`starts.generate` は使用しない。`fresh_system_tmp_path` はまだ存在しない、checkout外の
system tmp内ディレクトリとする。`solver_kind='fixture'` は既存Workerと同じラベルであり、
solver自体の置換はしない（テストが明示patchする）。通常の既定値は `scipy`。
`spot_checks={'terminal': [0]}` 等は全JobのJobSpecに凍結する既存Workerの引数を利用する。

## 凍結・予約・状態

- 全seed×armを既存 `controller.actions` の固定順で列挙し、**投入前に全Job**を
  `freeze_development_job()` で凍結。Plan/definition/RF/grid/source/solver/startを照合する。
- Workerの既存 `trial_id='development_only'` は変更しない。親Job行の `trial_id='seed23'`
  などで各seedを独立Trialへ対応付ける。全記録はdevelopment専用で、G1承認とは呼ばない。
- 各Trialに全armのJob cap合計を事前予約し、preflightの予約合計と一致・Trial cap以下を検査。
  Campaignは集計のみで、Campaign capは作らない。
- Jobの `cap = requested + reserved + released`。未開始Jobはcap全額を予約する。
  正常照合済みJobのみ `released = cap - requested` として未要求枠を解放する。
- 起動前に親 `run.json` のJobを `unknown` としてatomic保存。次Jobの依存は固定順の前Jobのみ。
  `completed` は**親による取込確定**であり、Workerの収束やRFのPASSとは別。
- 不明な結果ではcapを保持する。照合可能な異常rawならrequested/completedを観測費用として記録し、
  残りを予約に保持する。照合不能なら費用は未確定のままcap全額を予約する。
  `unknown_cost_upper_bound` は当該Jobのcapを示す。これは全額実行済みという推定ではない。
- 不明Job以降は別Trialも含め全体STOP。自動retry/resume・未解決枠の再利用をしない。
  親保存に失敗したら例外を伝播し、in-memory successで再保存するfinalizerは持たない。

## raw読戻しと証拠

Worker返却snapshotをそのまま結果として採用せず、実rawファイルを読戻す。
既存 `storage.atomic` のbyte encodingとsnapshotの一致を確認し、さらにJobSpec束縛、
RF/Plan/definition/全grid SHA、batch allocation/grid、各batchのrequested/completed、
job total、残余・予約、独立spot費用を検査する。

- `raw_byte_sha256`: **実ファイルのbytes**のSHA。
- `raw_content_sha256`: 読戻したJSONのcanonical content SHA（改行を含まない）。
- `spec_sha256`: JobSpecのcanonical SHA。Job ID/seed/arm/start/sourceはspecを通じて束縛。

snapshotとの比較は偶発改変・取込不整合の検出であり、悪意あるWorkerを認証するものではない。
親はRF再計算・独自solver・費用のnfev推定を持たない。

`worker_status` と `exit_reason` を別欄に保存し、`not_converged` / `budget_exhausted` を
取込失敗やRF判定と混ぜない。`evidence` はterminal/anytime/dense/独立spotを区別し、
各観測の `strict_feasible` と格子SHAを保持する。未実施は `not_run` のまま。
`solver_nfev`、primary `requested/completed`、`independent_requested/completed` は別欄。
親Campaign全体の数値RF合格判定・G0–G5承認は導入しない。

## 限定検証・raw例

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=tests uv run --frozen python -m unittest -v test_issue319_parent_runner
```

9テスト。実RFは `test_real_f003_two_arms_tiny_fixture_and_readback` の1 seed×2 armsのみ。
既存fixture solverは同じ合法xを返し、各Jobは全6設定・28個別区間を評価する。

| 各Jobの内訳 | points/interval | primary requested/completed |
|---|---:|---:|
| coarse（callback 2回） | 2 | 112/112 |
| anytime（1 milestone） | 3 | 84/84 |
| selection（同一xは1候補） | 3 | 84/84 |
| terminal | 4 | 112/112 |
| 合計 | — | **392/392** |

各Job cap=1500、Trial cap=3000、初期予約3000。
全Job取込後、Trial requested/completed=784/784、reserved=0、released=2216。
各Jobのsolverは `not_converged`、nfev=999（意図的にsample数と無関係）。
独立terminal spotは各Jobで1 sample、計2/2（primary 784に加算しない）。
finite-grid observationの適否は各assessmentの値のまま保存し、独立spotを全帯域検証としない。
denseは `not_run`。

親rawの構造例（SHA等は実行時生成、完全rawは一時ディレクトリのみ）：

```json
{
  "kind": "stage4c2_development_only",
  "status": "completed",
  "gates": {"G0_G1": "not_ready", "G2_G5": "not_ready"},
  "campaign": {
    "status": "completed", "requested": 784, "completed": 784,
    "reserved": 0, "released": 2216,
    "independent_requested": 2, "independent_completed": 2,
    "unknown_cost_upper_bound": 0
  }
}
```

その他はWorker mockによる正常／未収束／予算停止／異常・unknown・例外・中断・
raw欠落/改変/数値不整合・親保存障害・親取込直前停止の検証。
別seed=別Trialの独立費用集計、全額予約→確定後のみ解放、後続全停止を検査する。
通常smokeとsparse CIに同じテストを追加した。
RF-F003 effective SHAは `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。
T006 full-LPF scan、新EXP、本番探索、連続帯域保証、Q(f)/SRF/EM/実測は実行・認定していない。
