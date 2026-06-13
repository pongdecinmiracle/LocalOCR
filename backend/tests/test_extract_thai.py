from __future__ import annotations

import io

from PIL import Image

from app import config, extract


def _make_page(tmp_path):
    Image.new("RGB", (40, 40), "white").save(tmp_path / "page_0.png")
    (tmp_path / "page_0.txt").write_text("anchor text layer", encoding="utf-8")


def test_thai_ocr_mode_two_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXTRACT_MODE", "thai-ocr")
    _make_page(tmp_path)

    seen = {}

    def fake_ocr_page(png, anchor):
        seen["anchor"] = anchor
        return "## สลิปเงินเดือน\nเงินเดือน (Salary): 27,000.00"

    def fake_text_extract(prompt, *, model, as_json):
        seen["prompt"] = prompt
        seen["model"] = model
        return '{"salary": "27,000.00"}'

    monkeypatch.setattr(extract, "ocr_page", fake_ocr_page)
    monkeypatch.setattr(extract, "text_extract", fake_text_extract)
    monkeypatch.setattr(
        extract, "vision_extract", lambda *a, **k: (_ for _ in ()).throw(AssertionError("vlm path used"))
    )

    template = {
        "fields": [
            {
                "name": "salary",
                "label": "เงินเดือน",
                "type": "number",
                "page": 0,
                "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05},
            }
        ]
    }
    res = extract.extract_document(tmp_path, template, "qwen2.5vl:7b")

    assert res["fields"]["salary"] == 27000
    # The PDF text layer reached Typhoon as anchor text.
    assert seen["anchor"] == "anchor text layer"
    # Stage two received the OCR text and the field definition.
    assert "เงินเดือน" in seen["prompt"]
    assert "สลิปเงินเดือน" in seen["prompt"]
    assert seen["model"] == "qwen2.5vl:7b"


def test_template_mode_overrides_server_default(tmp_path, monkeypatch):
    # Server default is vlm, but the template requests the Thai pipeline.
    monkeypatch.setattr(config, "EXTRACT_MODE", "vlm")
    _make_page(tmp_path)
    monkeypatch.setattr(extract, "ocr_page", lambda png, anchor: "เงินเดือน: 99")
    monkeypatch.setattr(
        extract, "text_extract", lambda prompt, *, model, as_json: '{"salary": 99}'
    )
    monkeypatch.setattr(
        extract, "vision_extract", lambda *a, **k: (_ for _ in ()).throw(AssertionError("vlm path used"))
    )
    template = {
        "extract_mode": "thai-ocr",
        "fields": [
            {
                "name": "salary",
                "label": "เงินเดือน",
                "type": "number",
                "page": 0,
                "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05},
            }
        ],
    }
    res = extract.extract_document(tmp_path, template, "m")
    assert res["fields"]["salary"] == 99


def test_template_extract_mode_persists(client):
    from conftest import register

    register(client)
    body = {
        "name": "Thai Invoice",
        "extract_mode": "thai-ocr",
        "fields": [
            {"name": "a", "type": "text", "page": 0, "box": {"x": 0, "y": 0, "w": 1, "h": 1}}
        ],
    }
    tid = client.post("/api/templates", json=body).json()["id"]
    assert client.get(f"/api/templates/{tid}").json()["extract_mode"] == "thai-ocr"

    # Invalid/empty values are dropped -> follows the server default.
    body["id"] = tid
    body["extract_mode"] = "bogus"
    client.post("/api/templates", json=body)
    assert "extract_mode" not in client.get(f"/api/templates/{tid}").json()


def test_vlm_mode_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXTRACT_MODE", "vlm")
    _make_page(tmp_path)
    monkeypatch.setattr(extract, "vision_extract", lambda *a, **k: '{"total": 5}')
    template = {
        "fields": [
            {
                "name": "total",
                "label": "Total",
                "type": "number",
                "page": 0,
                "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05},
            }
        ]
    }
    res = extract.extract_document(tmp_path, template, "m")
    assert res["fields"]["total"] == 5
