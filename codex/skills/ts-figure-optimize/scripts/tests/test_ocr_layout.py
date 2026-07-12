import importlib.util
import json
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit", SCRIPTS / "audit_ocr_layout.py")
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


def _files(tmp_path, boxes):
    ocr = tmp_path / "ocr.json"; ir = tmp_path / "box_ir.json"
    ocr.write_text(json.dumps({"ocr_text_boxes": boxes}))
    ir.write_text(json.dumps({"canvas": {"width": 1000, "height": 500}}))
    return ocr, ir


def test_detects_severe_text_overlap(tmp_path):
    ocr, ir = _files(tmp_path, [
        {"id": "T1", "text": "Encoder", "bbox": [100, 100, 300, 140]},
        {"id": "T2", "text": "Decoder", "bbox": [180, 105, 330, 145]},
    ])
    report = audit.audit(ocr, ir)
    assert not report["ok"] and report["collisions"]


def test_allows_separated_labels(tmp_path):
    ocr, ir = _files(tmp_path, [
        {"id": "T1", "text": "Encoder", "bbox": [100, 100, 300, 140]},
        {"id": "T2", "text": "Decoder", "bbox": [400, 100, 600, 140]},
    ])
    assert audit.audit(ocr, ir)["ok"]
