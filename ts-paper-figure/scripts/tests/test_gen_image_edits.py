import importlib.util, pathlib, sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))  # so gen_image's `import _dotenv` resolves
spec = importlib.util.spec_from_file_location("gen_image", SCRIPTS / "gen_image.py")
gi = importlib.util.module_from_spec(spec); spec.loader.exec_module(gi)


def test_build_edits_request_single_ref(tmp_path):
    ref = tmp_path / "ref.png"; ref.write_bytes(b"\x89PNG\r\n\x1a\nDUMMY")
    url, body, ctype = gi._build_edits_request(
        base="https://x/v1", model="gpt-image-2", prompt="P",
        refs=[str(ref)], size="1536x1024")
    assert url == "https://x/v1/images/edits"
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="model"' in body and b"gpt-image-2" in body
    assert b'name="prompt"' in body and b"P" in body
    assert b'name="image"' in body and b"DUMMY" in body
    assert b'name="size"' in body and b"1536x1024" in body


def test_build_edits_request_multi_ref_uses_image_array(tmp_path):
    a = tmp_path / "a.png"; a.write_bytes(b"AAAA")
    b = tmp_path / "b.png"; b.write_bytes(b"BBBB")
    _, body, _ = gi._build_edits_request(base="https://x/v1", model="gpt-image-2",
                                         prompt="P", refs=[str(a), str(b)], size="1024x1024")
    assert body.count(b'name="image[]"') == 2


def test_render_routes_to_edits_when_refs_present(monkeypatch, tmp_path):
    called = {}

    def fake_post_multipart(url, body, ctype, key, timeout=300):
        called["url"] = url
        import base64
        return {"data": [{"b64_json": base64.b64encode(b"\x89PNG\r\n\x1a\nX").decode()}]}

    monkeypatch.setenv("TS_FIG_API_KEY", "k"); monkeypatch.setenv("TS_FIG_BASE_URL", "https://x/v1")
    monkeypatch.setenv("TS_FIG_MODEL", "gpt-image-2"); monkeypatch.setenv("TS_FIG_API_STYLE", "images")
    monkeypatch.setattr(gi, "_post_multipart", fake_post_multipart)
    ref = tmp_path / "r.png"; ref.write_bytes(b"\x89PNG\r\n\x1a\nR")
    out = tmp_path / "o.png"
    res = gi.render("P", out, references=[str(ref)])
    assert res["ok"] and res["path"] == "edits" and called["url"].endswith("/images/edits")


def test_render_falls_back_to_textonly_without_refs(monkeypatch, tmp_path):
    def fake_post_json(url, payload, key, timeout=180):
        import base64
        assert url.endswith("/images/generations")
        return {"data": [{"b64_json": base64.b64encode(b"\x89PNG\r\n\x1a\nY").decode()}]}

    monkeypatch.setenv("TS_FIG_API_KEY", "k"); monkeypatch.setenv("TS_FIG_BASE_URL", "https://x/v1")
    monkeypatch.setenv("TS_FIG_MODEL", "gpt-image-2"); monkeypatch.setenv("TS_FIG_API_STYLE", "images")
    monkeypatch.setattr(gi, "_post_json", fake_post_json)
    out = tmp_path / "o.png"
    res = gi.render("P", out)
    assert res["ok"] and res["path"] == "generations"
