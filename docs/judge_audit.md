# Judge audit

FAIL là lớp dương. Cả hai bộ CSV có 100 mẫu. Sàn κ/P/R lần lượt là 0.60/0.80/0.70.

| Judge | κ | P | R | TP/FP/FN/TN | Fail quan sát → hiệu chỉnh | Quyết định |
|---|---:|---:|---:|---|---|---|
| tone | 0.757 | 0.857 | 0.800 | 24/4/6/66 | 28% → 30% | PASS |
| helpful | 0.375 | 1.000 | 0.300 | 9/0/21/70 | 9% → 30% | FAIL |

| Case | Human / Judge | Ai đúng | Sửa rubric |
|---|---|---|---|
| H-008 | FAIL / PASS | Human | Thêm ví dụ về “nha” và “check giúp em” làm giọng quá suồng sã. |
| H-017 | FAIL / PASS | Human | Đánh giá cả lối gọi “bạn ơi” dù có từ “Dạ”. |
| H-029 | FAIL / PASS | Human | Xem “không cần nhắn thêm” là dấu hiệu gạt đi yêu cầu của khách. |
| H-042 | PASS / FAIL | Human | Chấp nhận câu ngắn, đủ thông tin, lịch sự dù thiếu lời xin lỗi. |
| H-051 | PASS / FAIL | Human | Chấp nhận từ “refund” nếu giọng và ý vẫn rõ. |

Helpful bỏ sót 21/30 lỗi và trượt sàn κ lẫn recall. Loại khỏi gate. Dùng code đối chiếu tiền với ledger. Các số liệu đến từ replay công khai, cần một tập held-out có nhãn human mới trước khi áp dụng rộng hơn.
