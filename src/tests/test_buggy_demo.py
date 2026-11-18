from lab8.demo.buggy_workflow import buggy_pay, demo_connection


def test_checkpoint_only_demo_pays_twice():
    conn = demo_connection()
    buggy_pay(conn, "C-001", 35000)
    count = conn.execute("SELECT COUNT(*) FROM demo_unsafe_refunds").fetchone()[0]
    conn.close()
    assert count == 2
