"""
ResumeXpert – Forms
"""

from django import forms


# ---------------------------------------------------------------------------
# Resume upload form
# ---------------------------------------------------------------------------
class ResumeUploadForm(forms.Form):
    full_name = forms.CharField(
        label="Your Full Name",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class':       'form-control',
            'placeholder': 'e.g. Priya Sharma (optional – auto-detected)',
        })
    )
    target_industry = forms.CharField(
        label="Target Industry / Role",
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'industryOptions',
            'placeholder': 'e.g. Software Dev, Sales, Electrical Installation...',
        })
    )
    resume_file = forms.FileField(
        label="Upload Your Resume",
        widget=forms.FileInput(attrs={
            'class':  'form-control',
            'accept': '.pdf,.docx,.jpg,.jpeg,.png',
            'id':     'resumeFile',
        })
    )
    job_description = forms.CharField(
        label="Paste Job Description",
        widget=forms.Textarea(attrs={
            'class':       'form-control',
            'rows':        7,
            'placeholder': 'Paste the full job description here. The more detail you provide, '
                           'the more accurate the ATS score and suggestions will be.',
        })
    )

    # ── Client-side offloading fields (written by upload_controller.js) ──────
    # Optional — not shown in the UI. The Web Worker fills these before submit.
    # The server uses them to skip expensive PyMuPDF / pdfplumber passes.
    client_extracted_text = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    client_file_type = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.HiddenInput(),
    )

    ALLOWED_EXTENSIONS = ('.pdf', '.docx', '.jpg', '.jpeg', '.png')

    def clean_resume_file(self):
        f = self.cleaned_data.get('resume_file')
        if f:
            name = f.name.lower()
            if not any(name.endswith(ext) for ext in self.ALLOWED_EXTENSIONS):
                raise forms.ValidationError(
                    "Only PDF, DOCX, JPG, and PNG files are supported."
                )
            if f.size > 50 * 1024 * 1024:   # 50 MB
                raise forms.ValidationError(
                    "File is too large. Maximum allowed size is 50 MB."
                )
        return f

    def clean_job_description(self):
        jd = self.cleaned_data.get('job_description', '').strip()
        if len(jd) < 30:
            raise forms.ValidationError(
                "Please provide a more detailed job description "
                "(at least 30 characters) for accurate analysis."
            )
        return jd


# ---------------------------------------------------------------------------
# Exam submission form
# ---------------------------------------------------------------------------
class ExamSubmitForm(forms.Form):
    """Dynamically built in the view – no fixed fields here."""
    pass
