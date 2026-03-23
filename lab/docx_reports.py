from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from django.conf import settings


@dataclass(frozen=True)
class DocxTemplateChoice:
    path: Path | None
    reason: str


def _reports_dir() -> Path:
    return Path(settings.BASE_DIR) / "reports"


def choose_docx_template_for_test_type(test_type_name: str | None, *, negative: bool) -> DocxTemplateChoice:
    """
    Pick a DOCX template from the repo's `reports/` directory.

    Heuristic (simple + robust):
    - Prefer templates that match the test type token (wes/wgs/sanger/cma/rna/...) in filename.
    - Prefer negative/negatif templates when negative=True.
    - Fall back to the first .docx found; if none exist, return None (caller will create a blank doc).
    """
    reports_dir = _reports_dir()
    if not reports_dir.exists():
        return DocxTemplateChoice(path=None, reason=f"{reports_dir} missing")

    candidates = sorted([p for p in reports_dir.glob("*.docx") if p.is_file()])
    if not candidates:
        return DocxTemplateChoice(path=None, reason=f"no .docx in {reports_dir}")

    name_l = (test_type_name or "").strip().lower()
    tokens: list[str] = []
    if "wes" in name_l:
        tokens.append("wes")
    if "wgs" in name_l:
        tokens.append("wgs")
    if "sanger" in name_l:
        tokens.append("sanger")
    if "cma" in name_l or "array" in name_l:
        tokens.append("cma")
    if "rna" in name_l:
        tokens.append("rna")
    if not tokens and name_l:
        tokens.append(name_l.split()[0])

    def score(p: Path) -> tuple[int, int, int]:
        fn = p.name.lower()
        neg_score = 0
        if negative:
            neg_score = 2 if any(t in fn for t in ("negatif", "negative", "neg")) else 0
        else:
            neg_score = 1 if not any(t in fn for t in ("negatif", "negative", "neg")) else 0

        token_score = 0
        for t in tokens:
            if t and t in fn:
                token_score = 3
                break

        length_score = -len(fn)
        return (token_score, neg_score, length_score)

    best = max(candidates, key=score)
    return DocxTemplateChoice(path=best, reason=f"best match among {len(candidates)} candidates")


def build_docx_report_bytes(
    *,
    template_path: Path | None,
    title: str,
    variants_rows: Iterable[dict],
    negative: bool,
) -> bytes:
    from docx import Document

    if template_path and template_path.exists():
        doc = Document(str(template_path))
    else:
        doc = Document()

    # Spacer
    doc.add_paragraph("")
    # Some legacy templates may not define "Heading 2"; fall back to a bold paragraph.
    try:
        doc.add_heading(title, level=2)
    except KeyError:
        p = doc.add_paragraph(title)
        run = p.runs[0] if p.runs else p.add_run(title)
        run.bold = True

    if negative:
        doc.add_paragraph("No clinically relevant variants were reported.")
    else:
        table = doc.add_table(rows=1, cols=4)
        hdr = table.rows[0].cells
        hdr[0].text = "Location"
        hdr[1].text = "Zygosity"
        hdr[2].text = "Type"
        hdr[3].text = "Genes"

        for row in variants_rows:
            cells = table.add_row().cells
            cells[0].text = str(row.get("location") or "")
            cells[1].text = str(row.get("zygosity") or "")
            cells[2].text = str(row.get("type") or "")
            cells[3].text = str(row.get("genes") or "")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()

