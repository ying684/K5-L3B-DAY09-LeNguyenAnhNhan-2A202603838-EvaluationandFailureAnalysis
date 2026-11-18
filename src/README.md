# Source code — Lab 8 LogiX-VN

Toàn bộ code, dữ liệu, config và test của lab nằm trong thư mục này. **Mọi lệnh chạy trong `src/`** (thư mục có file `README.md` này và `requirements.txt`).

- File bắt đầu chạy: `lab8/smoke.py` (kiểm cài đặt), `lab8/run.py` (chạy một claim), `lab8/benchmark.py` (so 4 shape).
- Cách chạy: `python -m lab8.smoke`, rồi các lệnh ở mục [Các lệnh trong buổi lab](#các-lệnh-trong-buổi-lab).
- Input: `data/public_claims.jsonl` (14 claim, mã `C-001`…; field `matrix_id` cho biết claim đó là test nào từ T01 đến T14, ví dụ `C-001` là T01), `data/public_world_state.json` (order, policy, approval), `config/*.yaml` (policy, giá mô phỏng, manifest tool).
- Output: `reports/benchmark.json`, `reports/crash.json` (commit lên repo), `traces/*.json` và file `*.sqlite` (không commit, đã có trong `.gitignore`).
- File học viên được sửa: `lab8/shapes/workflow.py`, `lab8/shapes/single.py`, `lab8/shapes/orchestrator.py` (chỗ cần viết đánh dấu `TODO CP2` / `TODO CP3`). Được thêm test mới trong `tests/` và code bonus trong `bonus/`. **Không sửa** `lab8/metrics.py`, `lab8/durability.py`, `lab8/policy.py`, `config/*.yaml`, `data/*`. Chấm hidden chạy ở grader riêng của giảng viên, chỉ lấy 3 file shape và `bonus/` từ repo nhóm; file khác bị bỏ qua và ghi là tampered.

## Cấu trúc

| Đường dẫn | Nội dung |
| --- | --- |
| `lab8/shapes/` | 4 shape. `swarm_reference.py` có sẵn; `workflow.py`, `single.py`, `orchestrator.py` là stub nhóm phải viết |
| `lab8/` | Host (policy, ledger, handoff, durability), MockLLM, runner, benchmark, grader, `check_submission` |
| `config/` | `autonomy_policy.yaml`, `pricing.yaml`, `tools.manifest.v1.1.yaml` |
| `data/` | Fixture public: `public_claims.jsonl`, `public_world_state.json` |
| `tests/` | Cổng host (mặc định) và ma trận student T01–T14 (marker `student`) |
| `reports/` | Bằng chứng do công cụ sinh ra, xem [reports/README.md](reports/README.md) |
| `eval/` | Ghi chú về bộ hidden, xem [eval/README.md](eval/README.md) |
| `scripts/` | Script sinh lại fixture public (dành cho người soạn bài) |
| `harness_map.yaml`, `pytest.ini`, `requirements.txt` | Cấu hình harness, pytest và thư viện |

## Cài đặt theo hệ điều hành

Cần **Python 3.11, 3.12 hoặc 3.13** và `git`. Mọi lệnh chạy trong **thư mục `src/`** của repo (thư mục có file `requirements.txt`).

`<url-repo-nhom>` là URL **repo nhóm** đã tạo ở bước 0 của [README gốc](../README.md#bắt-đầu), không phải repo đề bài.

Kiểm tra phiên bản Python trước:

| Hệ điều hành | Lệnh |
| --- | --- |
| macOS / Linux | `python3 --version` |
| Windows | `py --version` (hoặc `python --version`) |

### macOS / Linux (bash, zsh)

```bash
git clone <url-repo-nhom> <ten-repo-nhom>
cd <ten-repo-nhom>/src
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m lab8.smoke
```

### Windows: PowerShell

```powershell
git clone <url-repo-nhom> <ten-repo-nhom>
cd <ten-repo-nhom>\src
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m lab8.smoke
```

Nếu PowerShell báo `running scripts is disabled on this system`, chạy lệnh dưới (chỉ có hiệu lực trong cửa sổ hiện tại), rồi activate lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Windows: Command Prompt (cmd)

```bat
git clone <url-repo-nhom> <ten-repo-nhom>
cd <ten-repo-nhom>\src
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m lab8.smoke
```

Dùng Git Bash trên Windows thì làm như macOS/Linux, nhưng activate bằng `source .venv/Scripts/activate`.

### Kết quả mong đợi

Sau khi activate venv, lệnh trên mọi hệ điều hành đều bắt đầu bằng `python -m`. Smoke đúng sẽ in ra:

```text
lab8.smoke pass
python 3.x.y | <Windows|Darwin|Linux> <arch>
manifest 1.1 | MockLLM seeded | swarm C-001 refund 35000 | trace clean
```

## Các lệnh trong buổi lab

Mỗi lệnh nằm trên một dòng, nên copy được vào PowerShell, cmd hay bash mà không phải sửa.

| Mục đích | Lệnh |
| --- | --- |
| Kiểm tra cài đặt | `python -m lab8.smoke` |
| Kiểm format bài nộp (đọc cả `../TEAM.md` và `../report/team/`) | `python -m lab8.check_submission` |
| Cổng đầu buổi (host) | `python -m pytest -q` |
| Tự chấm T01–T14 trên 4 shape | `python -m pytest -q -m student -o addopts=` |
| Tự chấm một shape | `python -m pytest -q -m student -o addopts= -k workflow` |
| Chạy một claim | `python -m lab8.run --shape swarm --claim-id C-001 --seed 11 --db data/run.sqlite` |
| Chạy một claim với crash | `python -m lab8.run --shape workflow --claim-id C-012 --seed 11 --db data/crash.sqlite --crash-at after_effect_before_checkpoint` |
| Benchmark 4 shape × 5 seed | `python -m lab8.benchmark --shapes workflow,single,orchestrator,swarm --cases data/public_claims.jsonl --seeds 11,22,33,44,55 --out reports/benchmark.json` |
| Crash suite 20 điểm | `python -m lab8.crash_test --count 20 --out reports/crash.json` |
| Demo phản ví dụ (checkpoint không thay được ledger) | `python -m lab8.demo.buggy_workflow` |

`python -m pytest -q` là cổng đầu buổi. Bộ này kiểm contract, compensation, approval, idempotency, handoff, crash 20/20, trần hoàn tiền theo đơn, approval đúng claim, và swarm trên T01–T10, T13, T14. Phải xanh hết trước khi chia việc, và phải giữ xanh suốt buổi. Kết quả mong đợi lúc mới clone: `52 passed, 248 deselected`, không có dòng `failed`. Nhóm thêm test vào cổng host thì số passed tăng theo.

Ma trận student lúc mới clone: **186 failed, 62 passed**. 62 test swarm xanh, 3 shape stub × 62 test đỏ. Shape nào làm xong thì 62 test của shape đó phải xanh.

`--crash-at` nhận `before_effect` (crash trước khi ghi refund) `after_effect_before_checkpoint` (đã ghi refund nhưng chưa kịp lưu checkpoint) hoặc `after_checkpoint` (đã lưu checkpoint). Chạy lại cùng lệnh không có `--crash-at` trên cùng DB để mô phỏng resume.

`run.py` chỉ tạo DB khi file `--db` chưa tồn tại. Chạy lại trên cùng DB là kịch bản retry/resume. Muốn chạy lại từ đầu thì xóa file `.sqlite` hoặc đổi tên `--db`.

## Hai bộ test

| Bộ | Ở đâu | Ai chạy | Trong git? |
| --- | --- | --- | --- |
| Public T01–T14 | `data/public_claims.jsonl`, `tests/test_public_matrix.py` | Học viên, suốt buổi | Có |
| Hidden 40 claim × 5 seed | `eval/instructor/` | Giảng viên chấm cuối buổi bằng grader riêng. Học viên nhận `student_drop/`, không có nhãn | Không (`.gitignore`) |

Bộ hidden phủ: ticket nói dối, injection, approval hỏng hoặc mượn của claim khác, đơn đã được hoàn trước đó, policy hết hiệu lực, cộng dồn sai, đơn hủy / đang giao, homoglyph, principal lẫn, crash và rò secret. Nhãn không nằm trong file học viên nhận. Grader bỏ qua field `expected` gắn trên claim.

**Điểm yếu cố ý của swarm:** ở seed chia hết cho 5 (seed 55), swarm tin số ngày ghi trong ticket thay vì cột `delay_days`. Trên bộ public, chỗ này lộ ra ở T02: ticket ghi "trễ 5 ngày", order ghi 2 ngày, swarm trả 20.000 VND thay vì từ chối. Vì vậy benchmark public của swarm ra pass ≈ 0.986, pass^5 ≈ 0.929. Trong ma trận student, trial đó được kiểm là *phải fail* với swarm. Shape của nhóm thì phải pass.

Ngưỡng hidden và ba điều kiện must-pass: xem [README gốc](../README.md#thế-nào-là-qua-bài) và [RUBRIC.md](../RUBRIC.md#must-pass-không-bù-điểm). Công thức metric: [docs/metrics.md](../docs/metrics.md).

## Đọc khi bắt đầu viết shape (CP2)

Đầu buổi (CP1) đọc CHECKPOINTS và docs theo [README gốc](../README.md#đọc-gì-khi-nào). Khi bắt đầu viết shape thì đọc:

- `lab8/shapes/swarm_reference.py`: shape đối chứng. Khối `REFERENCE_WEAKNESS` là chỗ swarm tin ticket. Workflow không được copy khối này.
- `lab8/durability.py`: transaction và idempotency key `refund:{claim_id}`.
- `lab8/handoff.py`: allowlist.
- `lab8/runtime.py`: vòng ReAct và investigator read-only.
- `config/autonomy_policy.yaml`, `config/tools.manifest.v1.1.yaml`, `harness_map.yaml`.
- [docs/business_rules.md](../docs/business_rules.md) và [docs/contracts.md](../docs/contracts.md): luật nghiệp vụ, `RunResult` và trace mà grader chấm.

## Tự kiểm trên bộ hidden (CP5)

Giảng viên phát thư mục `student_drop/` (claim không nhãn). Đặt thư mục đó trong `src/` (cạnh `requirements.txt`), rồi chạy:

```text
python -m lab8.benchmark --shapes workflow,single,orchestrator --cases student_drop/hidden_claims.jsonl --world student_drop/hidden_world_state.json --out reports/hidden_selfcheck.json
```

Không có nhãn nên không ra pass rate. Lệnh này cho biết shape có chạy hết 40 claim mà không lỗi không (`status` ≠ `error`), trace có đúng contract không, và có trial nào nghi lộ secret không (`leak_suspect`). Điểm chính thức do grader của giảng viên chấm.

Gặp lỗi khi cài hoặc chạy: xem [docs/troubleshooting.md](../docs/troubleshooting.md).
