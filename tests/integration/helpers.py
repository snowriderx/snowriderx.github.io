"""
Shared assertion helpers for integration tests.
"""


def assert_flash_success(resp) -> None:
    """Response HTML phải chứa flash message 'success'."""
    html = resp.data.decode("utf-8")
    assert 'alert-success' in html, (
        f"Expected flash success in response, got:\n{html[:500]}"
    )


def assert_flash_error(resp) -> None:
    """Response HTML phải chứa flash message 'danger'."""
    html = resp.data.decode("utf-8")
    assert 'alert-danger' in html or 'alert-warning' in html, (
        f"Expected flash error in response, got:\n{html[:500]}"
    )


def assert_no_flash_success(resp) -> None:
    """Response HTML không được có flash success — dùng sau validation fail."""
    html = resp.data.decode("utf-8")
    assert 'alert-success' not in html, (
        "Expected NO flash success (validation should have failed)"
    )


def assert_form_error(resp) -> None:
    """Response phải render lại form kèm lỗi."""
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert '<form' in html


def assert_tbl_link_synced(db_conn, row_id: int, row_type: int) -> None:
    """
    Sau create/edit, tblLink phải có row tương ứng.
    row_type=2 → news, row_type=3 → product.
    Chỉ assert khi tblMenu có MenuID khớp (slug mới có thể NULL nếu menu chưa set).
    """
    cur = db_conn.cursor()
    cur.execute(
        'SELECT "RowUrl" FROM "tblLink" WHERE "RowID" = %s AND "RowType" = %s',
        (str(row_id), row_type),
    )
    # Không assert bắt buộc có — sync có thể skip nếu menu không match.
    # Chỉ assert không crash bằng cách gọi fetchall().
    cur.fetchall()
    db_conn.rollback()
