import importlib.util
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("remote_runtime", SCRIPTS / "remote_runtime.py")
remote_runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = remote_runtime
spec.loader.exec_module(remote_runtime)

ENGINE = SCRIPTS.parent / "engine"


def _health_payload(*, sam3_device="cuda:0", include_ocr=True):
    services = {
        "sam3": {"endpoint": "/v1/segment/proposals", "device": sam3_device},
        "rmbg": {"endpoint": "/v1/rmbg/remove-background", "device": "cuda:0"},
    }
    if include_ocr:
        services["ocr"] = {"endpoint": "/v1/ocr/boxes", "device": "cpu"}
    return {"status": "ok", "services": services}


def _serve(payload, required_auth=""):
    state = {"requests": 0, "auth": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            state["requests"] += 1
            state["auth"].append(self.headers.get("Authorization"))
            if required_auth and self.headers.get("Authorization") != required_auth:
                self.send_response(401)
                self.end_headers()
                return
            if self.path not in {"/health", "/v1/health"}:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


def _set_base(monkeypatch, base_url, key=""):
    monkeypatch.setenv("DRAWAI_REMOTE_BASE_URL", base_url)
    monkeypatch.setenv("DRAWAI_REMOTE_SAM3_URL", "")
    monkeypatch.setenv("DRAWAI_REMOTE_OCR_URL", "")
    monkeypatch.setenv("DRAWAI_REMOTE_RMBG_URL", "")
    monkeypatch.setenv("DRAWAI_REMOTE_API_KEY", key)
    monkeypatch.setenv("DRAWAI_REMOTE_API_KEY_HEADER", "Authorization")
    monkeypatch.setenv("DRAWAI_REMOTE_API_KEY_SCHEME", "Bearer")
    monkeypatch.setenv("DRAWAI_REMOTE_HEALTH_ATTEMPTS", "1")


def test_authenticated_health_and_secret_free_resolved_config(tmp_path, monkeypatch):
    server, state = _serve(_health_payload(), required_auth="Bearer secret-token")
    try:
        _set_base(monkeypatch, f"http://127.0.0.1:{server.server_port}", "secret-token")
        settings = remote_runtime.load_settings()
        report = remote_runtime.probe(settings)
        assert report["ok"] is True
        assert state["auth"] == ["Bearer secret-token"]

        output = tmp_path / "resolved.yaml"
        remote_runtime.write_resolved_config(
            ENGINE / "configs/drawai/config.yaml", output, settings
        )
        assert remote_runtime.validate_binding(output, settings) == []
        text = output.read_text()
        assert "secret-token" not in text
        assert f"127.0.0.1:{server.server_port}" in text
    finally:
        server.shutdown()
        server.server_close()


def test_health_contract_rejects_missing_service(monkeypatch):
    server, _state = _serve(_health_payload(include_ocr=False))
    try:
        _set_base(monkeypatch, f"http://127.0.0.1:{server.server_port}")
        report = remote_runtime.probe(remote_runtime.load_settings())
        assert report["ok"] is False
        assert any("ocr is absent" in item for item in report["errors"])
    finally:
        server.shutdown()
        server.server_close()


def test_health_contract_rejects_cpu_heavy_model(monkeypatch):
    server, _state = _serve(_health_payload(sam3_device="cpu"))
    try:
        _set_base(monkeypatch, f"http://127.0.0.1:{server.server_port}")
        report = remote_runtime.probe(remote_runtime.load_settings())
        assert report["ok"] is False
        assert any("sam3 heavy model" in item for item in report["errors"])
    finally:
        server.shutdown()
        server.server_close()


def test_non_loopback_cleartext_and_url_credentials_are_rejected(monkeypatch):
    _set_base(monkeypatch, "http://example.invalid:18080")
    try:
        remote_runtime.load_settings()
        raise AssertionError("non-loopback clear-text HTTP was accepted")
    except ValueError as exc:
        assert "clear-text HTTP" in str(exc)

    _set_base(monkeypatch, "https://user:password@example.invalid")
    try:
        remote_runtime.load_settings()
        raise AssertionError("credentials embedded in URL were accepted")
    except ValueError as exc:
        assert "must not contain credentials" in str(exc)

    _set_base(monkeypatch, "https://example.invalid?token=secret")
    try:
        remote_runtime.load_settings()
        raise AssertionError("query credentials embedded in URL were accepted")
    except ValueError as exc:
        assert "query credentials" in str(exc)


def test_binding_detects_tampering(tmp_path, monkeypatch):
    _set_base(monkeypatch, "http://127.0.0.1:18080")
    settings = remote_runtime.load_settings()
    output = tmp_path / "resolved.yaml"
    remote_runtime.write_resolved_config(ENGINE / "configs/drawai/config.yaml", output, settings)
    output.write_text(output.read_text().replace("127.0.0.1:18080", "127.0.0.1:9999", 1))
    assert any("sam3 remote binding mismatch" in item
               for item in remote_runtime.validate_binding(output, settings))


def test_health_attempt_budget_is_hard_capped(monkeypatch):
    _set_base(monkeypatch, "http://127.0.0.1:1")
    monkeypatch.setenv("DRAWAI_REMOTE_HEALTH_ATTEMPTS", "99")
    try:
        remote_runtime.load_settings()
        raise AssertionError("unbounded health attempts were accepted")
    except ValueError as exc:
        assert "between 1 and 3" in str(exc)

    monkeypatch.setenv("DRAWAI_REMOTE_HEALTH_ATTEMPTS", "1")
    monkeypatch.setenv("DRAWAI_REMOTE_QUEUE_MAX_POLLS", "301")
    try:
        remote_runtime.load_settings()
        raise AssertionError("unbounded queue poll budget was accepted")
    except ValueError as exc:
        assert "between 1 and 300" in str(exc)


def test_auth_header_rejects_injection(monkeypatch):
    from drawai.http_utils import remote_service_headers

    monkeypatch.setenv("DRAWAI_REMOTE_API_KEY", "secret")
    monkeypatch.setenv("DRAWAI_REMOTE_API_KEY_HEADER", "Authorization\r\nX-Evil")
    try:
        remote_service_headers()
        raise AssertionError("invalid remote header name was accepted")
    except ValueError as exc:
        assert "valid HTTP header name" in str(exc)


def test_nonretryable_ocr_queue_timeout_is_not_multiplied(tmp_path):
    from drawai.ocr_provider import OcrHttpStatusError, RemotePaddleOcrProvider

    class BusyTransport:
        calls = 0

        def post_json(self, _path, _payload, _timeout_s):
            self.calls += 1
            raise OcrHttpStatusError("queue budget exhausted", http_status=503, retryable=False)

    transport = BusyTransport()
    provider = RemotePaddleOcrProvider(
        "http://127.0.0.1:18080", 30, transport=transport, retry_max_attempts=5,
        sleep=lambda _seconds: (_ for _ in ()).throw(AssertionError("unexpected retry sleep")),
    )
    image = tmp_path / "source.png"
    image.write_bytes(b"input-bytes")
    try:
        provider.extract_boxes(image)
        raise AssertionError("nonretryable OCR failure was accepted")
    except OcrHttpStatusError:
        pass
    assert transport.calls == 1


def test_ocr_retry_budget_rejects_values_above_hard_cap():
    from drawai.ocr_provider import OcrProviderError, RemotePaddleOcrProvider

    try:
        RemotePaddleOcrProvider("http://127.0.0.1:18080", 30, retry_max_attempts=6)
        raise AssertionError("OCR retry budget above five was accepted")
    except OcrProviderError as exc:
        assert "between 1 and 5" in str(exc)
