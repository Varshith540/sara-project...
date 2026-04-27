# ResumeXpert – AI-Powered Resume Analyser

An intelligent resume analysis system that evaluates resumes using ATS scoring,
provides skill gap analysis, improvement suggestions, and skill-based exams.

---

## Tech Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Backend    | Django 4.2, Python 3.10+               |
| ML / NLP   | Scikit-learn (TF-IDF, Cosine Sim)      |
| Parsing    | PyPDF2 (PDF), python-docx (DOCX)       |
| Frontend   | Bootstrap 5, Chart.js, Custom CSS/JS   |
| Database   | SQLite (dev) — swap to PostgreSQL prod |

---

## Project Structure

```
resumexpert/
├── manage.py
├── requirements.txt
├── README.md
├── db.sqlite3                  ← auto-created on first migrate
├── media/                      ← uploaded resumes
├── static/
│   ├── css/style.css
│   └── js/main.js
├── resumexpert/                ← Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── core/                       ← Main application
    ├── models.py               ← DB models
    ├── views.py                ← Request handlers
    ├── urls.py                 ← URL patterns
    ├── forms.py                ← Django forms
    ├── admin.py                ← Admin registration
    ├── resume_parser.py        ← PDF / DOCX text extraction
    ├── nlp_processor.py        ← Skill extraction + cosine similarity
    ├── scoring_engine.py       ← Hybrid ATS scoring logic
    ├── exam_generator.py       ← Quiz question bank + generator
    ├── templatetags/
    │   └── resume_filters.py   ← Custom template filters
    └── templates/core/
        ├── base.html
        ├── upload.html
        ├── dashboard.html
        ├── exam.html
        ├── exam_result.html
        └── history.html
```

---

## Setup & Run (Step-by-Step)

### 1 — Clone / extract project

```bash
cd resumexpert/
```

### 2 — Create virtual environment

```bash
python -m venv venv

# Activate:
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### 4 — Apply database migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5 — Create admin user (optional)

```bash
python manage.py createsuperuser
```

### 6 — Run the development server

```bash
python manage.py runserver
```

Open your browser at: **http://127.0.0.1:8000/**

Admin panel: **http://127.0.0.1:8000/admin/**

---

## How to Use

1. Go to **http://127.0.0.1:8000/**
2. Upload your resume (PDF or DOCX, max 5 MB)
3. Paste the job description in the text area
4. Click **Analyse Resume**
5. View your ATS Score, Skill Match %, matched/missing skills, and suggestions
6. Click **Take Skill Exam** to test your knowledge

---

## ATS Scoring Formula

| Component          | Weight | Description                                 |
|--------------------|--------|---------------------------------------------|
| Skill Match Score  | 50%    | % of JD skills found in resume              |
| Cosine Similarity  | 30%    | TF-IDF text relevance between resume and JD |
| Resume Completeness| 20%    | Checks for Education, Experience, Skills, Projects, Contact |
| Keyword Bonus      | +5     | Bonus for high keyword density              |

**Total ATS Score = capped at 100%**

---

## Key Pages

| URL                    | Page             |
|------------------------|------------------|
| `/`                    | Upload Resume    |
| `/dashboard/<id>/`     | Analysis Results |
| `/exam/<id>/`          | Skill Exam       |
| `/exam/<id>/submit/`   | Exam Results     |
| `/history/`            | All Past Results |
| `/admin/`              | Django Admin     |

---

## Troubleshooting

**PDF text is empty** → The PDF may be a scanned image. Use a text-based PDF.

**Skills not detected** → Ensure skills are spelled as standard terms (e.g., "Python" not "Py").

**Static files not loading** → Run `python manage.py collectstatic` for production.

**Port already in use** → Run on a different port: `python manage.py runserver 8080`
