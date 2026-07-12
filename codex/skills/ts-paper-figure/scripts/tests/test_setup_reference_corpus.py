import importlib.util
import json
import pathlib
import zipfile

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_refs", SCRIPTS / "setup_reference_corpus.py")
setup_refs = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup_refs)


def test_installs_valid_corpus_from_archive(tmp_path):
    source = tmp_path / "source" / "PaperBananaBench"
    for task in ("diagram", "plot"):
        root = source / task; (root / "images").mkdir(parents=True)
        (root / "images" / "ref.png").write_bytes(b"image")
        (root / "ref.json").write_text(json.dumps([{"id": f"r{i}"} for i in range(10)]))
    archive = tmp_path / "refs.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(source.parent))
    installed = setup_refs.install_archive(archive, tmp_path / "cache")
    assert setup_refs.valid_corpus(installed)[0]


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "bad")
    try:
        setup_refs._safe_extract(archive, tmp_path / "out")
    except RuntimeError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("unsafe archive member was accepted")


def test_install_repairs_upstream_utf8_mojibake_filename(tmp_path):
    source = tmp_path / "source" / "PaperBananaBench"
    expected = "Diffusion Tree inference‑time_diagram.jpg"
    mojibake = expected.encode("utf-8").decode("cp437")
    for task in ("diagram", "plot"):
        root = source / task
        (root / "images").mkdir(parents=True)
        image_name = mojibake if task == "diagram" else "plot.jpg"
        ref_name = expected if task == "diagram" else image_name
        (root / "images" / image_name).write_bytes(b"image")
        (root / "ref.json").write_text(json.dumps([
            {"id": f"r{i}", "path_to_gt_image": f"images/{ref_name}"} for i in range(10)
        ]))
    archive = tmp_path / "refs.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(source.parent))

    installed = setup_refs.install_archive(archive, tmp_path / "cache")

    assert (installed / "diagram" / "images" / expected).is_file()
    assert setup_refs.valid_corpus(installed)[0]
    repairs = json.loads((installed / "FILENAME_REPAIRS.json").read_text())["repairs"]
    assert repairs and repairs[0]["to"].endswith(expected)


def test_valid_corpus_rejects_missing_referenced_images(tmp_path):
    for task in ("diagram", "plot"):
        root = tmp_path / task
        (root / "images").mkdir(parents=True)
        (root / "images" / "present.jpg").write_bytes(b"image")
        (root / "ref.json").write_text(json.dumps([
            {"id": f"r{i}", "path_to_gt_image": "images/missing.jpg"} for i in range(10)
        ]))
    ok, issues = setup_refs.valid_corpus(tmp_path)
    assert not ok
    assert any("missing images" in issue for issue in issues)
