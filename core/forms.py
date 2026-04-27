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
    resume_file = forms.FileField(
        label="Upload Your Resume",
        widget=forms.FileInput(attrs={
            'class':  'form-control',
            'accept': '.pdf,.docx',
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

    def clean_resume_file(self):
        f = self.cleaned_data.get('resume_file')
        if f:
            name = f.name.lower()
            if not (name.endswith('.pdf') or name.endswith('.docx')):
                raise forms.ValidationError(
                    "Only PDF and DOCX files are supported. "
                    "Please upload a file in one of those formats."
                )
            if f.size > 5 * 1024 * 1024:   # 5 MB
                raise forms.ValidationError(
                    "File is too large. Maximum allowed size is 5 MB."
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
