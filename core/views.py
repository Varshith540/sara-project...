"""
ResumeXpert – Views
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Resume, AnalysisResult, ExamAttempt
from .forms import ResumeUploadForm
from .resume_parser import extract_text, extract_email, extract_phone, extract_name
from .scoring_engine import calculate_score
from .exam_generator import generate_exam, get_available_skills


# ---------------------------------------------------------------------------
# Home / Upload view
# ---------------------------------------------------------------------------
def upload_resume(request):
    """Show the upload form and process submissions."""
    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file   = request.FILES['resume_file']
            job_description = form.cleaned_data['job_description']
            manual_name     = form.cleaned_data.get('full_name', '').strip()

            # ---- Save resume record (so we get a file path) ----------------
            resume = Resume(file=uploaded_file)
            resume.save()

            # ---- Extract text from the saved file --------------------------
            file_path = resume.file.path
            raw_text  = extract_text(file_path)

            if not raw_text:
                messages.error(
                    request,
                    "Could not read text from the uploaded file. "
                    "Please make sure the file is not a scanned image PDF."
                )
                resume.delete()
                return render(request, 'core/upload.html', {'form': form})

            # ---- Populate resume metadata ----------------------------------
            resume.raw_text = raw_text
            resume.name     = manual_name or extract_name(raw_text)
            resume.email    = extract_email(raw_text)
            resume.phone    = extract_phone(raw_text)
            resume.save()

            # ---- Run ATS scoring ------------------------------------------
            score_data = calculate_score(raw_text, job_description)

            result = AnalysisResult(
                resume            = resume,
                job_description   = job_description,
                ats_score         = score_data['ats_score'],
                skill_match_score = score_data['skill_match_score'],
                cosine_score      = score_data['cosine_score'],
                matched_skills    = score_data['matched_skills'],
                missing_skills    = score_data['missing_skills'],
                resume_skills     = score_data['resume_skills'],
                suggestions       = score_data['suggestions'],
            )
            result.save()

            messages.success(request, "Resume analysed successfully! 🎉")
            return redirect('dashboard', pk=result.pk)

        # Form has errors – re-render
        return render(request, 'core/upload.html', {'form': form})

    else:
        form = ResumeUploadForm()

    return render(request, 'core/upload.html', {'form': form})


# ---------------------------------------------------------------------------
# Dashboard view
# ---------------------------------------------------------------------------
def dashboard(request, pk):
    """Display full analysis results for a single resume."""
    result = get_object_or_404(AnalysisResult, pk=pk)

    # Build chart-ready JSON for radar/bar charts
    chart_data = {
        'labels': ['Skill Match', 'Content Relevance', 'Resume Completeness'],
        'values': [
            round(result.skill_match_score, 1),
            round(result.cosine_score, 1),
            round(
                result.ats_score
                - result.skill_match_score * 0.5
                - result.cosine_score * 0.3,
                1
            ),
        ],
    }

    context = {
        'result':     result,
        'resume':     result.resume,
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'core/dashboard.html', context)


# ---------------------------------------------------------------------------
# History view
# ---------------------------------------------------------------------------
def history(request):
    """Show all past analysis results."""
    results = AnalysisResult.objects.select_related('resume').all()
    return render(request, 'core/history.html', {'results': results})


# ---------------------------------------------------------------------------
# Exam view
# ---------------------------------------------------------------------------
def exam_view(request, pk):
    """Show a skill-based quiz for the given analysis result."""
    result    = get_object_or_404(AnalysisResult, pk=pk)
    # Use matched skills first; fall back to all resume skills
    skills    = result.matched_skills or result.resume_skills
    questions = generate_exam(skills, num_questions=10)

    # Store questions in session so we can score the submission
    request.session[f'exam_{pk}_questions'] = questions

    context = {
        'result':    result,
        'questions': questions,
        'total':     len(questions),
    }
    return render(request, 'core/exam.html', context)


# ---------------------------------------------------------------------------
# Exam submit view
# ---------------------------------------------------------------------------
@require_POST
def exam_submit(request, pk):
    """Score the submitted exam answers and show results."""
    result    = get_object_or_404(AnalysisResult, pk=pk)
    questions = request.session.get(f'exam_{pk}_questions', [])

    if not questions:
        messages.warning(request, "Session expired. Please take the exam again.")
        return redirect('exam', pk=pk)

    answers     = {}
    score       = 0
    detailed    = []

    for idx, q in enumerate(questions):
        key          = f"q_{idx}"
        chosen_str   = request.POST.get(key, "")
        try:
            chosen = int(chosen_str)
        except ValueError:
            chosen = -1

        correct    = q['correct_index']
        is_correct = (chosen == correct)
        if is_correct:
            score += 1

        answers[str(idx)] = chosen
        detailed.append({
            'question':      q['question'],
            'skill':         q['skill'],
            'options':       q['options'],
            'chosen':        chosen,
            'correct_index': correct,
            'is_correct':    is_correct,
            'explanation':   q.get('explanation', ''),
        })

    # Save attempt
    attempt = ExamAttempt.objects.create(
        result  = result,
        score   = score,
        total   = len(questions),
        answers = answers,
    )

    # Clear session
    request.session.pop(f'exam_{pk}_questions', None)

    context = {
        'result':   result,
        'attempt':  attempt,
        'detailed': detailed,
        'score':    score,
        'total':    len(questions),
        'percent':  attempt.percentage(),
    }
    return render(request, 'core/exam_result.html', context)


# ---------------------------------------------------------------------------
# Delete result view
# ---------------------------------------------------------------------------
def delete_result(request, pk):
    """Delete an analysis result and its associated resume file."""
    result = get_object_or_404(AnalysisResult, pk=pk)
    resume = result.resume
    result.delete()
    try:
        resume.file.delete(save=False)
    except Exception:
        pass
    resume.delete()
    messages.success(request, "Record deleted successfully.")
    return redirect('history')
