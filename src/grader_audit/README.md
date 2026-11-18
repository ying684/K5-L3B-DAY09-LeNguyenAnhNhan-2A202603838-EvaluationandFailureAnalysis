# Kiểm toán grader (bonus B7)

Thư mục này do giảng viên cung cấp. Học viên không sửa file trong đây; test của nhóm đặt ở `src/tests/test_bonus_*.py`. Mọi lệnh chạy trong `src/`.

Có ba bản `summarize` ứng viên: `grader_a.py`, `grader_b.py`, `grader_c.py`. Mỗi bản nhận `list[dict]` trial và trả `dict[shape, stats]` với cùng khóa như `lab8.metrics.summarize`. Mỗi trial có các khóa mà `metrics.summarize` đọc (`shape`, `claim_id`, `seed`, `passed`, `cost_estimate`, `steps`, `model_calls`, `tool_calls`, `reason`) cộng thêm `infra_error` (`true` khi trial chết vì timeout hoặc crash hạ tầng, không phải vì quyết định sai của shape).

Không bản nào được chú thích hay đặt tên theo chất lượng. Việc của nhóm là tìm ra bản nào lệch, bằng bằng chứng chạy được.

## Quan hệ metamorphic

Quan hệ metamorphic không cần biết đáp án đúng tuyệt đối. Nó chỉ nói: đổi input theo cách này thì output phải đổi (hoặc không đổi) theo cách kia.

| Fixture | Cặp input | Quan hệ phải đúng |
| --- | --- | --- |
| `fixtures/metamorphic_claim_delay.json` | Hai claim giống hệt nhau, khác `delay_days` (2 so với 3), cùng policy `POL-2026-11`, clause `SHIP-LATE-03` có `min_delay_days` 3 | Quyết định phải đổi: 2 ngày không đủ điều kiện, 3 ngày đủ. Số tiền chỉ đổi từ 0 sang phí ship. Kiểm bằng `lab8.compensation.quote` với `policies` và `as_of` trong fixture. Fixture này kiểm quyết định nghiệp vụ, không đi qua `summarize` |
| `fixtures/metamorphic_infra.json` | Danh sách trial `a`, và `b` = `a` cộng thêm các trial `infra_error: true` | Pass rate trên các trial được chấm không đổi. Các trial hạ tầng không được coi là quyết định sai của shape |
| `fixtures/metamorphic_duplicate.json` | Danh sách trial `a`, và `b` = `a` lặp lại hai lần | Các tỉ lệ (`pass_rate`, `pass_5`, `seed_pass_rates`, `cost_per_success_vnd`, các giá trị trung bình) không đổi. Các tổng (`trials`, `graded_trials`, `successes`, `total_simulated_cost_vnd`) gấp đôi |

Mỗi fixture là một object có `relation` (tên quan hệ), `a`, `b`. Đọc bằng `json.load`.

## Cách dùng

```bash
python -m pytest -q tests/test_grader_audit_smoke.py
```

Smoke test chỉ kiểm ba module import được và trả về `dict`. Nó không nói bản nào đúng.
