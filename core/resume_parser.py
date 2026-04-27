"""
ResumeXpert – Resume Parser
Extracts raw text, name, email, and phone from PDF / DOCX resumes.
"""

import re
import os


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def extract_text(file_path: str) -> str:
    """
    Return raw text from a resume file.
    Supports .pdf and .docx.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext == '.docx':
        return _extract_docx(file_path)
    else:
        return ""


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------
def _extract_pdf(path: str) -> str:
    try:
        import PyPDF2
        text = ""
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"[ResumeParser] PDF error: {e}")
        return ""


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------
def _extract_docx(path: str) -> str:
    try:
        from docx import Document
        doc = Document(path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        paragraphs.append(cell.text.strip())
        return "\n".join(paragraphs).strip()
    except Exception as e:
        print(f"[ResumeParser] DOCX error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------
def extract_email(text: str) -> str:
    """Return the first email address found in the text."""
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    match = re.search(pattern, text)
    return match.group() if match else ""


def extract_phone(text: str) -> str:
    """Return the first phone number found in the text."""
    pattern = r'(\+?\d[\d\s\-().]{8,}\d)'
    match = re.search(pattern, text)
    if match:
        phone = re.sub(r'\s+', ' ', match.group()).strip()
        return phone[:20]
    return ""


def extract_name(text: str) -> str:
    """
    Heuristic: the candidate name is usually on the first non-empty line
    that is not an email, URL, or phone number.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    skip_patterns = re.compile(
        r'(@|http|www\.|linkedin|github|resume|curriculum|vitae|\d{7,})',
        re.IGNORECASE
    )
    for line in lines[:6]:
        if not skip_patterns.search(line) and len(line.split()) <= 5:
            # Looks like a name (short, no special markers)
            return line.title()
    return lines[0].title() if lines else "Candidate"


def extract_sections(text: str) -> dict:
    """
    Split the resume text into labelled sections such as
    Education, Experience, Skills, Projects, etc.
    Returns a dict {section_name: section_text}.
    """
    section_headers = [
        'education', 'experience', 'work experience', 'skills',
        'technical skills', 'projects', 'certifications', 'achievements',
        'summary', 'objective', 'publications', 'languages', 'hobbies',
        'internship', 'training', 'volunteer', 'awards',
    ]

    # Build regex that matches any header (case-insensitive, on its own line)
    header_regex = re.compile(
        r'^\s*(' + '|'.join(re.escape(h) for h in section_headers) + r')\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE
    )

    sections = {}
    lines = text.split('\n')
    current_section = 'header'
    current_lines = []

    for line in lines:
        if header_regex.match(line):
            sections[current_section] = '\n'.join(current_lines).strip()
            current_section = line.strip().lower().rstrip(':').strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_section] = '\n'.join(current_lines).strip()
    return sections
