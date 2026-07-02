import threading

import httpx

from traceval.cli import _report_server


def test_serve_serves_report_html(tmp_path):
    (tmp_path / "report.html").write_text(
        "<html><body>hello traceval</body></html>", encoding="utf-8"
    )

    server = _report_server(tmp_path, 0)  # port 0: OS picks a free one
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/report.html", timeout=5)
        assert resp.status_code == 200
        assert "hello traceval" in resp.text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()
