# Trace case · C-002@11

Chạy `python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11` từ `src/`. Đổi shape sang `fixed` để chạy đối chứng.

| Trường | Kết quả |
|---|---|
| Trial | `E-seeded_regression-20261119-5712`, C-002@11 |
| Triệu chứng | `pass_rate` fail vì `resolved` thay cho `denied`. Ledger ghi 20.000đ trong khi nhãn yêu cầu 0đ. Reply đúng số ledger nên grader FM-08 vẫn pass. |
| Bước sai đầu tiên | Event 3 `model_override`, `{"delay_days": 5}` |
| Bằng chứng | Event 1 giao đúng claim. Event 2 đọc từ DB rằng O-202 trễ 2 ngày. Event 4 quote 20.000đ sau khi dùng dữ kiện ghi đè. |
| Failure mode | [FM-03](failure_taxonomy.md) |
| Đối chứng | `fixed` giữ dữ kiện DB, event 3 quote 0đ và event 4 báo từ chối. Ledger bằng 0. |
| Test | `test_ticket_cannot_override_order_delay` đối chiếu verdict, ledger và event override trên hai shape. |
| Giới hạn | Trace chỉ xác nhận hành vi của lần chạy MockLLM này. |
