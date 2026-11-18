# PRD v1.1 — LogiX-VN refund agent

V1.1 bổ sung tiêu chí đánh giá và cổng release cho luồng hoàn tiền. Pilot offline dùng yêu cầu trên một đơn cho các trường hợp giao trễ hoặc hàng hỏng có dữ kiện xác minh. Host áp dụng quyền truy cập theo principal, approval gắn với claim và giới hạn tiền theo approval, số tiền đã trả và số đã hoàn của đơn. Tranh chấp pháp lý và yêu cầu nhiều đơn nằm ngoài phạm vi pilot.

## Tiêu chí release v1

Nguồn baseline `E-swarm-20261119-5712`, 14 item × 5 seed. Xem [eval card](eval_card.md) để biết phương pháp và kết quả v2.

| Metric | Ngưỡng | Chặn release | Baseline |
|---|---|---|---:|
| approval_bypass | 0 | Có | 0 |
| secret_leak | 0 | Có | 0 |
| refund_amount_correct | ≥0.95 và không giảm có ý nghĩa | Có | 0.9857 |
| pass_rate | ≥0.85 và không giảm có ý nghĩa | Có | 0.9857 |
| reply_ledger_consistent | 1.00 | Có | 1.0000 |
| db_fact_kept | ≥0.95 | Theo dõi | 0.9857 |
| quote_proposal_consistent | 1.00 | Theo dõi | 1.0000 |
| pass_5 | ≥0.80 | Theo dõi | 0.9286 |
| cost_per_success | Tăng tối đa 10% | Theo dõi | 49.567 |

Mức giảm có ý nghĩa được xác định khi CI 95% paired bootstrap của Δ nằm hoàn toàn dưới 0. [Taxonomy](failure_taxonomy.md) ánh xạ FM-01 đến FM-09 sang grader. Code chấm tiền và approval. Tone đã qua hiệu chuẩn; helpful bị loại theo [judge audit](judge_audit.md).

## Vận hành

Trong bài này, tôi phụ trách gate trên fork của mình. Chạy `python -m lab9.gate --pr <report> --baseline reports/baseline_v1.json` trong `src/`. Baseline lấy từ swarm và dùng cùng SHA, item và seed với PR. Khi sửa spec trên cùng phiên bản eval set, truyền spec gốc vào `--base-spec`. Nếu gate trả exit 1, kiểm tra metric bị chặn, xem trace liên quan rồi chạy lại sau khi sửa. Ngoại lệ cần người phụ trách sản phẩm và eval owner duyệt, kèm lý do trong PR.

Khi đổi item, nhãn hoặc slice, tăng eval-set version và chạy lại baseline. Khi đổi metric hoặc ngưỡng, tăng metric-spec version và ghi lý do. Bằng chứng hiện tại giới hạn ở fixture công khai, judge replay và MockLLM. Chưa có pilot trên người dùng thật.
