"""
Stage 6.2: Professional Dependency-Free PDF & DOCX Resume Exporter (`backend/services/resume_exporter.py`).

Generates valid, non-empty, standards-compliant:
- PDF 1.4 documents with template-aware typography, word wrapping, automatic
  multi-page pagination, section divider rules, and clickable URI link annotations.
- OpenXML (.docx) packages with template-aware styling, section borders, bullet
  formatting, and clickable hyperlinks.

Requires zero external system binaries or optional third-party libraries.
"""
import io
import re
import textwrap
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape
import zipfile

from backend.api.schemas import TailoredResumeContentSchema

_SECTION_TITLES: Dict[str, str] = {
    "summary": "Professional Summary",
    "education": "Education",
    "research_interests": "Research Interests",
    "skills": "Skills",
    "projects": "Selected Projects",
    "research_experience": "Research Experience",
    "experience": "Internships & Work Experience",
    "publications": "Publications",
    "achievements": "Achievements & Certifications",
}

_TEMPLATE_STYLES: Dict[str, Dict[str, str]] = {
    "academic_research": {
        "pdf_regular": "Times-Roman",
        "pdf_bold": "Times-Bold",
        "docx_font": "Georgia",
        "accent_hex": "1E3A5F",
        "accent_rgb": "0.118 0.227 0.373",
    },
    "modern_professional": {
        "pdf_regular": "Helvetica",
        "pdf_bold": "Helvetica-Bold",
        "docx_font": "Calibri",
        "accent_hex": "1B365D",
        "accent_rgb": "0.106 0.212 0.365",
    },
    "technical_ai_ml": {
        "pdf_regular": "Helvetica",
        "pdf_bold": "Helvetica-Bold",
        "docx_font": "Segoe UI",
        "accent_hex": "0F2942",
        "accent_rgb": "0.059 0.161 0.259",
    },
}


def _safe_ascii_pdf(text: str) -> str:
    """Converts common Unicode punctuation cleanly to Latin-1/PDF-safe text and escapes PDF parens."""
    replacements = {
        "\u2013": "-",
        "\u2014": "--",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u00b7": "|",
        "\u2026": "...",
    }
    cleaned = text
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = cleaned.encode("latin-1", errors="replace").decode("latin-1")
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _valid_link_url(raw: Optional[str]) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    val = raw.strip()
    if re.match(r"^(https?://|mailto:)[^\s]+$", val, re.I):
        return val
    if val.startswith("10."):
        return f"https://doi.org/{val}"
    return None


def _active_sections(content: TailoredResumeContentSchema) -> List[str]:
    enabled = set(content.enabled_sections)
    return [sec for sec in content.section_order if sec in enabled]


def _header_links(content: TailoredResumeContentSchema) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    if content.header.email:
        links.append((content.header.email, f"mailto:{content.header.email}"))
    linkedin = _valid_link_url(content.header.linkedin_url)
    if linkedin:
        links.append(("LinkedIn", linkedin))
    github = _valid_link_url(content.header.github_url)
    if github:
        links.append(("GitHub", github))
    portfolio = _valid_link_url(content.header.portfolio_url)
    if portfolio:
        links.append(("Portfolio", portfolio))
    return links


# =========================================================================
# PDF 1.4 Exporter
# =========================================================================

class _PdfBuilder:
    PAGE_W = 612.0  # US Letter width in pt
    PAGE_H = 792.0  # US Letter height in pt
    MARGIN_X = 50.0
    MARGIN_TOP = 50.0
    MARGIN_BOTTOM = 50.0

    def __init__(self, template: str):
        style = _TEMPLATE_STYLES.get(template, _TEMPLATE_STYLES["academic_research"])
        self.font_regular = style["pdf_regular"]
        self.font_bold = style["pdf_bold"]
        self.accent_rgb = style["accent_rgb"]
        self.pages: List[Tuple[List[str], List[Tuple[float, float, float, float, str]]]] = []
        self.y = self.PAGE_H - self.MARGIN_TOP
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append(([], []))
        self.y = self.PAGE_H - self.MARGIN_TOP

    def _ensure_space(self, needed_pt: float) -> None:
        if self.y - needed_pt < self.MARGIN_BOTTOM:
            self._new_page()

    def _draw_text(
        self,
        text: str,
        x: float,
        size: float,
        bold: bool = False,
        rgb: str = "0.10 0.13 0.18",
        link_url: Optional[str] = None,
    ) -> None:
        cmds, annots = self.pages[-1]
        font_ref = "/F2" if bold else "/F1"
        safe = _safe_ascii_pdf(text)
        cmds.append(f"BT {rgb} rg {font_ref} {size:.1f} Tf 1 0 0 1 {x:.1f} {self.y:.1f} Tm ({safe}) Tj ET")
        if link_url:
            est_w = min(self.PAGE_W - self.MARGIN_X - x, max(24.0, len(text) * size * 0.52))
            annots.append((x, self.y - 2.0, x + est_w, self.y + size, link_url))

    def add_title(self, name: str, subtitle: Optional[str], contact_line: str, links: List[Tuple[str, str]]) -> None:
        self._ensure_space(60)
        self._draw_text(name, self.MARGIN_X, 18.0, bold=True, rgb=self.accent_rgb)
        self.y -= 18.0
        if subtitle:
            self._draw_text(subtitle, self.MARGIN_X, 10.0, bold=False, rgb="0.28 0.33 0.41")
            self.y -= 13.0
        if contact_line:
            self._draw_text(contact_line, self.MARGIN_X, 9.2, bold=False, rgb="0.32 0.38 0.45")
            self.y -= 13.0
        if links:
            x = self.MARGIN_X
            for idx, (label, url) in enumerate(links):
                display = label if idx == len(links) - 1 else f"{label}  |"
                self._draw_text(display, x, 9.0, bold=False, rgb=self.accent_rgb, link_url=url)
                x += max(42.0, len(display) * 5.1) + 8.0
                if x > self.PAGE_W - self.MARGIN_X - 60:
                    self.y -= 12.0
                    x = self.MARGIN_X
            self.y -= 12.0
        self.y -= 4.0

    def add_section_heading(self, title: str) -> None:
        self._ensure_space(34)
        self.y -= 6.0
        self._draw_text(title.upper(), self.MARGIN_X, 10.5, bold=True, rgb=self.accent_rgb)
        line_y = self.y - 3.5
        cmds, _ = self.pages[-1]
        cmds.append(
            f"{self.accent_rgb} RG 0.8 w {self.MARGIN_X:.1f} {line_y:.1f} m "
            f"{self.PAGE_W - self.MARGIN_X:.1f} {line_y:.1f} l S"
        )
        self.y -= 15.0

    def add_subheading(self, left: str, right: Optional[str] = None, url: Optional[str] = None) -> None:
        self._ensure_space(18)
        avail_chars = 72 if right else 92
        wrapped = textwrap.wrap(left, width=avail_chars) or [left]
        self._draw_text(wrapped[0], self.MARGIN_X, 10.0, bold=True, rgb="0.08 0.11 0.16", link_url=url)
        if right:
            est_w = len(right) * 4.8
            rx = max(self.MARGIN_X + 320.0, self.PAGE_W - self.MARGIN_X - est_w)
            self._draw_text(right, rx, 9.0, bold=False, rgb="0.38 0.44 0.52")
        self.y -= 13.0
        for extra in wrapped[1:]:
            self._ensure_space(13)
            self._draw_text(extra, self.MARGIN_X, 10.0, bold=True, rgb="0.08 0.11 0.16")
            self.y -= 13.0

    def add_paragraph(self, text: str, size: float = 9.5, indent: float = 0.0, rgb: str = "0.18 0.22 0.28") -> None:
        max_chars = max(40, int((self.PAGE_W - 2 * self.MARGIN_X - indent) / (size * 0.49)))
        for line in textwrap.wrap(text, width=max_chars) or [text]:
            self._ensure_space(size + 3.5)
            self._draw_text(line, self.MARGIN_X + indent, size, bold=False, rgb=rgb)
            self.y -= size + 3.2

    def add_bullet(self, text: str) -> None:
        max_chars = 88
        lines = textwrap.wrap(text, width=max_chars) or [text]
        for idx, line in enumerate(lines):
            self._ensure_space(13.0)
            prefix = "- " if idx == 0 else "  "
            self._draw_text(prefix + line, self.MARGIN_X + 8.0, 9.3, bold=False, rgb="0.16 0.20 0.26")
            self.y -= 12.5

    def add_spacer(self, pt: float = 5.0) -> None:
        self.y -= pt

    def build_bytes(self) -> bytes:
        objects: List[bytes] = []

        def add_obj(body: str) -> int:
            objects.append(body.encode("latin-1", errors="replace"))
            return len(objects)

        catalog_id = add_obj("")  # placeholder 1
        pages_id = add_obj("")    # placeholder 2
        f1_id = add_obj(f"<< /Type /Font /Subtype /Type1 /BaseFont /{self.font_regular} >>")
        f2_id = add_obj(f"<< /Type /Font /Subtype /Type1 /BaseFont /{self.font_bold} >>")

        page_ids: List[int] = []
        for cmds, annots in self.pages:
            stream_data = "\n".join(cmds).encode("latin-1", errors="replace")
            content_id = add_obj(
                f"<< /Length {len(stream_data)} >>\nstream\n{stream_data.decode('latin-1')}\nendstream"
            )
            annot_ids: List[int] = []
            for x1, y1, x2, y2, url in annots:
                safe_url = _safe_ascii_pdf(url)
                annot_id = add_obj(
                    f"<< /Type /Annot /Subtype /Link /Rect [{x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f}] "
                    f"/Border [0 0 0] /A << /S /URI /URI ({safe_url}) >> >>"
                )
                annot_ids.append(annot_id)
            annots_entry = (
                f" /Annots [{' '.join(f'{aid} 0 R' for aid in annot_ids)}]" if annot_ids else ""
            )
            page_id = add_obj(
                f"<< /Type /Page /Parent {pages_id} 0 R "
                f"/MediaBox [0 0 {self.PAGE_W:.0f} {self.PAGE_H:.0f}] "
                f"/Resources << /Font << /F1 {f1_id} 0 R /F2 {f2_id} 0 R >> >> "
                f"/Contents {content_id} 0 R{annots_entry} >>"
            )
            page_ids.append(page_id)

        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
        objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")

        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: List[int] = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(out.tell())
            out.write(f"{idx} 0 obj\n".encode("latin-1"))
            out.write(obj)
            out.write(b"\nendobj\n")

        xref_pos = out.tell()
        out.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("latin-1"))
        out.write(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
        )
        return out.getvalue()


def export_resume_pdf(content: TailoredResumeContentSchema, template: Optional[str] = None) -> bytes:
    """Exports a tailored resume to a multi-page, link-enabled PDF 1.4 document."""
    pdf = _PdfBuilder(template or content.template)

    subtitle_parts = [
        content.header.degree_program,
        content.header.department,
        content.header.institution,
    ]
    subtitle = " | ".join(p.strip() for p in subtitle_parts if p and p.strip()) or None
    contact_bits = [content.header.phone, content.header.current_year_or_semester]
    if content.header.graduation_year:
        contact_bits.append(f"Class of {content.header.graduation_year}")
    contact_line = " | ".join(b.strip() for b in contact_bits if b and b.strip())

    pdf.add_title(content.header.full_name, subtitle, contact_line, _header_links(content))

    for sec in _active_sections(content):
        if sec == "summary" and content.summary.strip():
            pdf.add_section_heading(_SECTION_TITLES[sec])
            pdf.add_paragraph(content.summary.strip())
        elif sec == "research_interests" and content.research_interests and content.research_interests.strip():
            pdf.add_section_heading(_SECTION_TITLES[sec])
            pdf.add_paragraph(content.research_interests.strip())
        elif sec == "education" and content.education:
            pdf.add_section_heading(_SECTION_TITLES[sec])
            for edu in content.education:
                heading = f"{edu.degree}" + (f", {edu.department_major}" if edu.department_major else "")
                pdf.add_subheading(f"{heading} — {edu.institution}", edu.duration)
                meta = []
                if edu.cgpa_or_percentage:
                    meta.append(f"Grade / CGPA: {edu.cgpa_or_percentage}")
                if edu.relevant_coursework:
                    meta.append(f"Coursework: {edu.relevant_coursework}")
                if meta:
                    pdf.add_paragraph(" | ".join(meta), size=9.0, rgb="0.30 0.35 0.42")
                pdf.add_spacer(4)
        elif sec == "skills" and content.skills:
            pdf.add_section_heading(_SECTION_TITLES[sec])
            for grp in content.skills:
                if grp.items:
                    pdf.add_paragraph(f"{grp.category}: {', '.join(grp.items)}", size=9.4)
        elif sec in ("projects", "research_experience"):
            items = content.projects if sec == "projects" else content.research_experience
            if items:
                pdf.add_section_heading(_SECTION_TITLES[sec])
                for proj in items:
                    meta_left = proj.title
                    role_org = " · ".join(p for p in [proj.role, proj.organization] if p)
                    if role_org:
                        meta_left = f"{proj.title} ({role_org})"
                    pdf.add_subheading(meta_left, proj.duration, url=_valid_link_url(proj.url))
                    if proj.technologies:
                        pdf.add_paragraph(f"Technologies: {proj.technologies}", size=8.9, rgb="0.32 0.38 0.46")
                    for b in proj.bullets:
                        pdf.add_bullet(b)
                    pdf.add_spacer(4)
        elif sec == "experience" and content.experience:
            pdf.add_section_heading(_SECTION_TITLES[sec])
            for exp in content.experience:
                left = f"{exp.role} — {exp.organization}" + (f" ({exp.location})" if exp.location else "")
                pdf.add_subheading(left, exp.duration)
                if exp.technologies:
                    pdf.add_paragraph(f"Technologies: {exp.technologies}", size=8.9, rgb="0.32 0.38 0.46")
                for b in exp.bullets:
                    pdf.add_bullet(b)
                pdf.add_spacer(4)
        elif sec == "publications" and content.publications:
            pdf.add_section_heading(_SECTION_TITLES[sec])
            for pub in content.publications:
                pdf.add_subheading(pub.title, pub.date, url=_valid_link_url(pub.doi_or_url))
                meta = " · ".join(p for p in [pub.authors, pub.venue] if p)
                if meta:
                    pdf.add_paragraph(meta, size=9.0, rgb="0.30 0.35 0.42")
                if pub.summary:
                    pdf.add_paragraph(pub.summary, size=9.2)
                pdf.add_spacer(4)
        elif sec == "achievements" and content.achievements:
            pdf.add_section_heading(_SECTION_TITLES[sec])
            for ach in content.achievements:
                left = ach.title + (f" — {ach.issuer}" if ach.issuer else "")
                pdf.add_subheading(left, ach.date, url=_valid_link_url(ach.credential_url))
                if ach.description:
                    pdf.add_paragraph(ach.description, size=9.2)
                pdf.add_spacer(3)

    return pdf.build_bytes()


# =========================================================================
# OpenXML DOCX Exporter
# =========================================================================

def export_resume_docx(content: TailoredResumeContentSchema, template: Optional[str] = None) -> bytes:
    """Exports a tailored resume to a valid OpenXML (.docx) document with clickable links."""
    style = _TEMPLATE_STYLES.get(template or content.template, _TEMPLATE_STYLES["academic_research"])
    font_name = style["docx_font"]
    accent = style["accent_hex"]

    rels: List[Tuple[str, str]] = []

    def register_link(url: str) -> str:
        rid = f"rId{len(rels) + 2}"  # rId1 is styles.xml
        rels.append((rid, url))
        return rid

    def run_xml(text: str, size_half_pt: int = 20, bold: bool = False, color: str = "1F2937") -> str:
        b_tag = "<w:b/>" if bold else ""
        return (
            f'<w:r><w:rPr><w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}"/>'
            f'{b_tag}<w:color w:val="{color}"/><w:sz w:val="{size_half_pt}"/></w:rPr>'
            f'<w:t xml:space="preserve">{xml_escape(text)}</w:t></w:r>'
        )

    def link_xml(label: str, url: str, size_half_pt: int = 19) -> str:
        rid = register_link(url)
        return (
            f'<w:hyperlink r:id="{rid}" w:history="1">'
            f'<w:r><w:rPr><w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}"/>'
            f'<w:color w:val="{accent}"/><w:u w:val="single"/><w:sz w:val="{size_half_pt}"/></w:rPr>'
            f'<w:t xml:space="preserve">{xml_escape(label)}</w:t></w:r></w:hyperlink>'
        )

    paragraphs: List[str] = []

    def add_p(inner_xml: str, space_before: int = 0, space_after: int = 80, border_bottom: bool = False, indent_left: int = 0) -> None:
        pbr = (
            f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="{accent}"/></w:pBdr>'
            if border_bottom
            else ""
        )
        ind = f'<w:ind w:left="{indent_left}"/>' if indent_left else ""
        paragraphs.append(
            f'<w:p><w:pPr>{pbr}<w:spacing w:before="{space_before}" w:after="{space_after}"/>{ind}</w:pPr>'
            f"{inner_xml}</w:p>"
        )

    # Header
    add_p(run_xml(content.header.full_name, size_half_pt=36, bold=True, color=accent), space_after=40)
    sub_bits = [content.header.degree_program, content.header.department, content.header.institution]
    sub_line = " | ".join(p.strip() for p in sub_bits if p and p.strip())
    if sub_line:
        add_p(run_xml(sub_line, size_half_pt=20, color="475569"), space_after=30)

    contact_bits = [content.header.phone, content.header.current_year_or_semester]
    if content.header.graduation_year:
        contact_bits.append(f"Class of {content.header.graduation_year}")
    contact_line = " | ".join(b.strip() for b in contact_bits if b and b.strip())
    if contact_line:
        add_p(run_xml(contact_line, size_half_pt=18, color="64748B"), space_after=30)

    h_links = _header_links(content)
    if h_links:
        parts = []
        for idx, (label, url) in enumerate(h_links):
            if idx > 0:
                parts.append(run_xml("  |  ", size_half_pt=18, color="94A3B8"))
            parts.append(link_xml(label, url, size_half_pt=18))
        add_p("".join(parts), space_after=120)

    def add_section_header(title: str) -> None:
        add_p(
            run_xml(title.upper(), size_half_pt=22, bold=True, color=accent),
            space_before=160,
            space_after=80,
            border_bottom=True,
        )

    for sec in _active_sections(content):
        if sec == "summary" and content.summary.strip():
            add_section_header(_SECTION_TITLES[sec])
            add_p(run_xml(content.summary.strip(), size_half_pt=20))
        elif sec == "research_interests" and content.research_interests and content.research_interests.strip():
            add_section_header(_SECTION_TITLES[sec])
            add_p(run_xml(content.research_interests.strip(), size_half_pt=20))
        elif sec == "education" and content.education:
            add_section_header(_SECTION_TITLES[sec])
            for edu in content.education:
                heading = f"{edu.degree}" + (f", {edu.department_major}" if edu.department_major else "")
                line = run_xml(f"{heading} — {edu.institution}", size_half_pt=20, bold=True)
                if edu.duration:
                    line += run_xml(f"  ({edu.duration})", size_half_pt=18, color="64748B")
                add_p(line, space_after=30)
                meta = []
                if edu.cgpa_or_percentage:
                    meta.append(f"Grade / CGPA: {edu.cgpa_or_percentage}")
                if edu.relevant_coursework:
                    meta.append(f"Coursework: {edu.relevant_coursework}")
                if meta:
                    add_p(run_xml(" | ".join(meta), size_half_pt=18, color="475569"), space_after=70)
        elif sec == "skills" and content.skills:
            add_section_header(_SECTION_TITLES[sec])
            for grp in content.skills:
                if grp.items:
                    add_p(
                        run_xml(f"{grp.category}: ", size_half_pt=20, bold=True)
                        + run_xml(", ".join(grp.items), size_half_pt=20),
                        space_after=40,
                    )
        elif sec in ("projects", "research_experience"):
            items = content.projects if sec == "projects" else content.research_experience
            if items:
                add_section_header(_SECTION_TITLES[sec])
                for proj in items:
                    role_org = " · ".join(p for p in [proj.role, proj.organization] if p)
                    heading = f"{proj.title} ({role_org})" if role_org else proj.title
                    line = run_xml(heading, size_half_pt=20, bold=True)
                    if proj.duration:
                        line += run_xml(f"  |  {proj.duration}", size_half_pt=18, color="64748B")
                    valid_u = _valid_link_url(proj.url)
                    if valid_u:
                        line += run_xml("  ", size_half_pt=18) + link_xml("[Link]", valid_u, size_half_pt=18)
                    add_p(line, space_after=30)
                    if proj.technologies:
                        add_p(
                            run_xml("Technologies: ", size_half_pt=18, bold=True, color="475569")
                            + run_xml(proj.technologies, size_half_pt=18, color="475569"),
                            space_after=30,
                        )
                    for b in proj.bullets:
                        add_p(run_xml(f"• {b}", size_half_pt=19), space_after=30, indent_left=260)
                    add_p("", space_after=30)
        elif sec == "experience" and content.experience:
            add_section_header(_SECTION_TITLES[sec])
            for exp in content.experience:
                left = f"{exp.role} — {exp.organization}" + (f" ({exp.location})" if exp.location else "")
                line = run_xml(left, size_half_pt=20, bold=True)
                if exp.duration:
                    line += run_xml(f"  |  {exp.duration}", size_half_pt=18, color="64748B")
                add_p(line, space_after=30)
                if exp.technologies:
                    add_p(run_xml(f"Technologies: {exp.technologies}", size_half_pt=18, color="475569"), space_after=30)
                for b in exp.bullets:
                    add_p(run_xml(f"• {b}", size_half_pt=19), space_after=30, indent_left=260)
        elif sec == "publications" and content.publications:
            add_section_header(_SECTION_TITLES[sec])
            for pub in content.publications:
                line = run_xml(pub.title, size_half_pt=20, bold=True)
                if pub.date:
                    line += run_xml(f" ({pub.date})", size_half_pt=18, color="64748B")
                valid_u = _valid_link_url(pub.doi_or_url)
                if valid_u:
                    line += run_xml("  ", size_half_pt=18) + link_xml("[DOI / Paper]", valid_u, size_half_pt=18)
                add_p(line, space_after=30)
                meta = " · ".join(p for p in [pub.authors, pub.venue] if p)
                if meta:
                    add_p(run_xml(meta, size_half_pt=18, color="475569"), space_after=30)
                if pub.summary:
                    add_p(run_xml(pub.summary, size_half_pt=19), space_after=60)
        elif sec == "achievements" and content.achievements:
            add_section_header(_SECTION_TITLES[sec])
            for ach in content.achievements:
                left = ach.title + (f" — {ach.issuer}" if ach.issuer else "")
                line = run_xml(left, size_half_pt=20, bold=True)
                if ach.date:
                    line += run_xml(f" ({ach.date})", size_half_pt=18, color="64748B")
                valid_u = _valid_link_url(ach.credential_url)
                if valid_u:
                    line += run_xml("  ", size_half_pt=18) + link_xml("[Credential]", valid_u, size_half_pt=18)
                add_p(line, space_after=30)
                if ach.description:
                    add_p(run_xml(ach.description, size_half_pt=19), space_after=50)

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="864" w:right="864" w:bottom="864" w:left="864"/></w:sectPr>'
        "</w:body></w:document>"
    )

    rel_entries = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ]
    for rid, url in rels:
        rel_entries.append(
            f'<Relationship Id="{rid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{xml_escape(url)}" TargetMode="External"/>'
        )
    doc_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rel_entries)
        + "</Relationships>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr>'
        f'<w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}"/>'
        '<w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults>'
        "</w:styles>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
        zf.writestr("word/styles.xml", styles_xml)
    return buf.getvalue()
