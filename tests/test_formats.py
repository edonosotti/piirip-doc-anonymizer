import csv
from pathlib import Path

import pytest

from piirip.cli import main
from piirip.engine import Redactor
from piirip.playbooks import load_playbook

TEXT = "Contact John Smith at john.smith@example.com or +1 212-555-0198. IP 192.168.1.10."
SECRETS = ["john.smith@example.com", "John Smith", "192.168.1.10"]


@pytest.fixture(scope="session")
def redactor():
    return Redactor(load_playbook("default"))


def run(path: Path) -> Path:
    assert main([str(path)]) == 0
    return path.with_name(f"{path.stem}.redacted{path.suffix}")


def test_playbooks(redactor):
    assert "PERSON" in redactor.entities
    all_ = Redactor(load_playbook("all"))
    assert set(redactor.entities) < set(all_.entities)
    assert "IT_FISCAL_CODE" in all_.entities


def test_custom_playbook(tmp_path, redactor):
    pb = tmp_path / "pb.yaml"
    pb.write_text("entities: [EMAIL_ADDRESS]\n")
    r = Redactor(load_playbook(str(pb)))
    out = r.redact_text(TEXT)
    assert "<EMAIL_ADDRESS>" in out and "John Smith" in out


def test_txt_md_html(tmp_path):
    for name, content in [("a.txt", TEXT), ("a.md", f"# Hi\n{TEXT}"), ("a.html", f"<p>Hi <b>{TEXT}</b></p><a href='mailto:john.smith@example.com'>x</a>")]:
        f = tmp_path / name
        f.write_text(content)
        out = run(f).read_text()
        assert not any(s in out for s in SECRETS), out


def test_csv(tmp_path):
    f = tmp_path / "a.csv"
    with f.open("w", encoding="utf-8", newline="") as source:
        writer = csv.writer(source)
        writer.writerow(["id", "details", "notes"])
        writer.writerow(["1", TEXT, "Quoted, value\nwith another line"])
        writer.writerow(["2", "john.smith@example.com", "42"])

    with run(f).open(encoding="utf-8", newline="") as output:
        rows = list(csv.reader(output))

    assert len(rows) == 3
    assert rows[0] == ["id", "details", "notes"]
    assert rows[1][0] == "1"
    assert rows[1][2] == "Quoted, value\nwith another line"
    assert rows[2] == ["2", "<EMAIL_ADDRESS>", "42"]
    assert not any(secret in "\n".join(cell for row in rows for cell in row) for secret in SECRETS)


def test_gui_redact_file(tmp_path, redactor):
    pytest.importorskip("tkinter")
    from piirip.gui import redact_file

    src = tmp_path / "a.txt"
    src.write_text(TEXT)
    dst = tmp_path / "out.txt"
    assert redact_file(src, dst, redactor) > 0
    assert not any(s in dst.read_text() for s in SECRETS)


def test_docx_split_runs(tmp_path):
    import docx

    d = docx.Document()
    p = d.add_paragraph("Contact ")
    p.add_run("John ").bold = True
    p.add_run("Smith at john.smith@")
    p.add_run("example.com.")
    d.add_table(1, 1).cell(0, 0).text = TEXT
    f = tmp_path / "a.docx"
    d.save(f)
    out = docx.Document(str(run(f)))
    text = "\n".join(p.text for p in out.paragraphs) + out.tables[0].cell(0, 0).text
    assert not any(s in text for s in SECRETS), text
    assert "<PERSON>" in text


def test_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = TEXT
    wb.active["A2"] = 42
    f = tmp_path / "a.xlsx"
    wb.save(f)
    ws = openpyxl.load_workbook(run(f)).active
    assert not any(s in ws["A1"].value for s in SECRETS)
    assert ws["A2"].value == 42


def test_odt(tmp_path):
    from odf.opendocument import OpenDocumentText, load
    from odf.text import P, Span
    from odf import teletype

    d = OpenDocumentText()
    p = P()
    p.addText("Contact ")
    s = Span()
    s.addText("John Smith")
    p.addElement(s)
    p.addText(" at john.smith@example.com. IP 192.168.1.10.")
    d.text.addElement(p)
    f = tmp_path / "a.odt"
    d.save(str(f))
    out = load(str(run(f)))
    text = "".join(teletype.extractText(x) for x in out.text.childNodes)
    assert not any(s in text for s in SECRETS), text


def test_pdf(tmp_path):
    import pymupdf as fitz

    d = fitz.open()
    d.new_page().insert_text((72, 72), TEXT)
    f = tmp_path / "a.pdf"
    d.save(f)
    out = fitz.open(str(run(f)))
    text = out[0].get_text()
    assert not any(s in text for s in SECRETS), text


def test_pdf_placeholder(tmp_path):
    import pymupdf as fitz

    d = fitz.open()
    d.new_page().insert_text((72, 72), TEXT)
    f = tmp_path / "a.pdf"
    d.save(f)
    assert main(["--pdf-style", "placeholder", str(f)]) == 0
    text = fitz.open(str(tmp_path / "a.redacted.pdf"))[0].get_text()
    assert not any(s in text for s in SECRETS), text
    assert "<" in text and "PERSON" in text
