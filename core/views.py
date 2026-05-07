"""
ResumeXpert – Views
"""

import json
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Resume, AnalysisResult, ExamAttempt
from .forms import ResumeUploadForm
from .resume_parser import extract_text, extract_email, extract_phone, extract_name
from .scoring_engine import calculate_score
from .exam_generator import generate_exam, get_available_skills
from .gemini_service import (
    analyze_resume_with_gemini,
    analyze_resume_image_with_gemini,
    generate_exam_questions_with_gemini,
    is_gemini_available,
    rewrite_resume_with_gemini,
)


# ---------------------------------------------------------------------------
# Home / Upload view
# ---------------------------------------------------------------------------
def upload_resume(request):
    """Show the upload form and process submissions."""
    if request.method == 'POST':
        # ── Terminal audit — confirm file is reaching Django on every POST ──
        _f = request.FILES.get('resume_file')
        print("\n====== UPLOAD POST AUDIT ======")
        print(f"  resume_file in FILES : {'resume_file' in request.FILES}")
        print(f"  File name            : {_f.name if _f else 'N/A'}")
        print(f"  File size (bytes)    : {_f.size if _f else 'N/A'}")
        print(f"  POST keys            : {list(request.POST.keys())}")
        print("================================\n")

        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file   = request.FILES['resume_file']
            job_description = form.cleaned_data['job_description']
            manual_name     = form.cleaned_data.get('full_name', '').strip()
            file_ext        = os.path.splitext(uploaded_file.name)[1].lower()
            is_image        = file_ext in ('.jpg', '.jpeg', '.png')

            # ---- Save resume record (so we get a file path) ----------------
            resume = Resume(file=uploaded_file)
            resume.save()
            file_path = resume.file.path

            # ---- Route: IMAGE → Vision AI  |  PDF/DOCX → Local Parser -----
            if is_image:
                print(f"[UPLOAD] Image resume detected ({file_ext}). Routing to Vision AI.")
                try:
                    vision_data = analyze_resume_image_with_gemini(file_path, job_description)
                except TimeoutError as te:
                    resume.delete()
                    messages.error(request, f"⏱️ Connection Timeout: {te}")
                    return render(request, 'core/upload.html', {'form': form})
                if not vision_data:
                    resume.delete()
                    messages.error(
                        request,
                        "⚠️ Vision AI could not analyse your resume image. "
                        "Please ensure the image is clear and well-lit, or upload a PDF/DOCX instead."
                    )
                    return render(request, 'core/upload.html', {'form': form})

                raw_text    = vision_data.pop('ocr_text', '') or '[Image resume — text extracted by Vision AI]'
                gemini_data = vision_data

            else:
                # ---- Local text extraction (PDF / DOCX) --------------------
                from .resume_parser import IMAGE_FILE_SENTINEL
                raw_text = extract_text(file_path)

                if raw_text == IMAGE_FILE_SENTINEL:
                    # Should not occur for PDF/DOCX — sentinel is only for explicit images
                    raw_text = ''

                if not raw_text and file_ext == '.pdf':
                    # ── Scanned / image-based PDF ────────────────────────────
                    # Text extraction failed; try Vision AI automatically.
                    print(f"[UPLOAD] PDF text empty — routing '{uploaded_file.name}' to Vision AI (scanned PDF).")
                    try:
                        vision_data = analyze_resume_image_with_gemini(file_path, job_description)
                    except TimeoutError as te:
                        resume.delete()
                        messages.error(request, f"⏱️ Connection Timeout: {te}")
                        return render(request, 'core/upload.html', {'form': form})
                    if not vision_data:
                        resume.delete()
                        messages.error(
                            request,
                            "⚠️ Scanning failed. The PDF appears to be scanned/image-based and "
                            "Vision AI could not read it. Please ensure the file is not "
                            "password-protected or corrupted, or try uploading a JPG/PNG photo instead."
                        )
                        return render(request, 'core/upload.html', {'form': form})

                    raw_text    = vision_data.pop('ocr_text', '') or '[Scanned PDF — text extracted by Vision AI]'
                    gemini_data = vision_data   # already has ai_summary, suggestions, etc.

                elif not raw_text:
                    # ── DOCX or other format returned empty ──────────────────
                    print(f"[UPLOAD AUDIT] Text extraction returned empty for: {uploaded_file.name}")
                    resume.delete()
                    messages.error(
                        request,
                        "⚠️ Scanning failed. Please ensure the file is not password-protected or corrupted."
                    )
                    return render(request, 'core/upload.html', {'form': form})

                else:
                    # ── Normal text-based PDF / DOCX ─────────────────────────
                    gemini_data = analyze_resume_with_gemini(raw_text, job_description)

            # ---- Populate resume metadata ----------------------------------
            resume.raw_text        = raw_text
            resume.name            = manual_name or extract_name(raw_text)
            resume.email           = extract_email(raw_text)
            resume.phone           = extract_phone(raw_text)
            resume.target_industry = form.cleaned_data.get('target_industry', '').strip()
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
                # Gemini AI fields
                ai_summary        = gemini_data.get('ai_summary', ''),
                ai_suggestions    = gemini_data.get('ai_suggestions', []),
                interview_questions = gemini_data.get('interview_questions', []),
                job_fit_score     = gemini_data.get('job_fit_score', 0),
                active_ai_model   = gemini_data.get('active_model', 'Gemini'),
            )
            result.save()

            messages.success(request, "Resume analysed successfully! 🎉")
            return redirect('dashboard', pk=result.pk)

        # Form has errors – re-render
        print("====== GHOST UPLOAD AUDIT ======")
        print(f"request.FILES present: {'resume_file' in request.FILES}")
        print(f"DEBUG: Form Errors -> {form.errors.as_data()}")
        print("================================")
        
        # Give explicit frontend feedback to the user
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
                
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
        'result':           result,
        'resume':           result.resume,
        'chart_data':       json.dumps(chart_data),
        'gemini_available': is_gemini_available(),
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
    result     = get_object_or_404(AnalysisResult, pk=pk)
    difficulty = request.GET.get('difficulty', 'Intermediate')

    # Use matched skills first; fall back to all resume skills
    skills    = result.matched_skills or result.resume_skills
    questions = generate_exam(skills, num_questions=10)

    # If static bank couldn't fill enough questions, use Gemini to generate more
    if len(questions) < 5 and skills:
        gemini_questions = generate_exam_questions_with_gemini(skills, num_questions=10, difficulty=difficulty)
        if gemini_questions:
            questions = gemini_questions

    # Store questions in session so we can score the submission
    request.session[f'exam_{pk}_questions']  = questions
    request.session[f'exam_{pk}_difficulty'] = difficulty

    context = {
        'result':     result,
        'questions':  questions,
        'total':      len(questions),
        'difficulty': difficulty,
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

    difficulty = request.session.get(f'exam_{pk}_difficulty', 'Intermediate')

    # Save attempt
    attempt = ExamAttempt.objects.create(
        result     = result,
        score      = score,
        total      = len(questions),
        answers    = answers,
        difficulty = difficulty,
        time_limit = 30,
    )

    # Clear session
    request.session.pop(f'exam_{pk}_questions', None)
    request.session.pop(f'exam_{pk}_difficulty', None)

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


# ---------------------------------------------------------------------------
# AI Resume Rewriter view
# ---------------------------------------------------------------------------
def generate_resume(request, pk):
    """Generate (or fetch cached) an AI-rewritten resume tailored to the JD."""
    result = get_object_or_404(AnalysisResult, pk=pk)

    # Allow force-regen by clearing cache
    if request.GET.get('regen') == '1':
        result.rewritten_resume  = ''
        result.improvement_notes = []
        result.resume_skills     = []
        result.save(update_fields=['rewritten_resume', 'improvement_notes', 'resume_skills'])

    # Use cached version if already generated
    if result.rewritten_resume:
        context = {
            'result':            result,
            'resume':            result.resume,
            'rewritten_resume':  result.rewritten_resume,
            'improvement_notes': result.improvement_notes,
            'gemini_available':  True,
            'from_cache':        True,
        }
        return render(request, 'core/resume_rewrite.html', context)

    # Check Gemini is available
    if not is_gemini_available():
        messages.error(
            request,
            "Gemini AI is not configured. Add your GEMINI_API_KEY to the .env file."
        )
        return redirect('dashboard', pk=pk)

    # Fetch skill test results
    attempts = result.attempts.all()
    if attempts.exists():
        exam_summary = [f"Difficulty: {a.difficulty}, Score: {a.percentage()}%" for a in attempts]
        exam_results_str = "Skill Test Validations: " + "; ".join(exam_summary)
    else:
        exam_results_str = "No skill tests taken."

    # Call Gemini to rewrite the resume
    rewrite_data = rewrite_resume_with_gemini(
        resume_text      = result.resume.raw_text,
        job_description  = result.job_description,
        missing_skills   = result.missing_skills,
        suggestions      = result.suggestions,
        exam_results     = exam_results_str,
        target_industry  = result.resume.target_industry,
    )

    if not rewrite_data or not rewrite_data.get('rewritten_resume'):
        messages.error(
            request,
            "Gemini could not generate the resume right now. Please try again."
        )
        return redirect('dashboard', pk=pk)

    # Cache in DB
    result.rewritten_resume  = rewrite_data['rewritten_resume']
    result.improvement_notes = rewrite_data.get('improvement_notes', [])
    result.active_ai_model   = rewrite_data.get('active_model', 'Gemini')
    if rewrite_data.get('skills'):
        result.resume_skills = rewrite_data['skills']
    result.save(update_fields=['rewritten_resume', 'improvement_notes', 'active_ai_model', 'resume_skills'])

    context = {
        'result':            result,
        'resume':            result.resume,
        'rewritten_resume':  result.rewritten_resume,
        'improvement_notes': result.improvement_notes,
        'gemini_available':  True,
        'from_cache':        False,
    }
    return render(request, 'core/resume_rewrite.html', context)


# ---------------------------------------------------------------------------
# Company Analysis view
# ---------------------------------------------------------------------------
def company_analysis(request, pk):
    """View to search and display company analysis using Gemini."""
    result = get_object_or_404(AnalysisResult, pk=pk)

    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        if company_name:
            from .gemini_service import analyze_company_with_gemini
            analysis = analyze_company_with_gemini(company_name, result.job_description)
            if analysis:
                result.company_name = company_name
                result.company_analysis = analysis
                result.save(update_fields=['company_name', 'company_analysis'])
                messages.success(request, f"Analysis for {company_name} completed!")
            else:
                messages.error(request, "Failed to analyze the company right now.")
        return redirect('company_analysis', pk=pk)

    context = {
        'result': result,
        'resume': result.resume,
        'gemini_available': is_gemini_available(),
    }
    return render(request, 'core/company_analysis.html', context)


# ---------------------------------------------------------------------------
# API: Get Trending Skills
# ---------------------------------------------------------------------------
def get_trending_skills(request):
    """API endpoint to get trending skills for a given sector asynchronously."""
    sector = request.GET.get('sector', 'IT / Software')
    from .gemini_service import get_trending_skills_with_gemini
    skills = get_trending_skills_with_gemini(sector)
    return JsonResponse({'skills': skills})


# ---------------------------------------------------------------------------
# AI Resume Builder (from scratch)
# ---------------------------------------------------------------------------
def resume_builder(request):
    """Form to generate a completely new resume using Gemini."""
    if request.method == 'POST':
        user_data = {
            'name':       request.POST.get('name', ''),
            'email':      request.POST.get('email', ''),
            'phone':      request.POST.get('phone', ''),
            'sector':     request.POST.get('sector', ''),
            'job_title':  request.POST.get('job_title', ''),
            'experience': request.POST.get('experience', ''),
            'skills':     request.POST.get('skills', ''),
            'summary':    request.POST.get('summary', ''),
        }

        from .gemini_service import build_resume_from_scratch_with_gemini
        build_data = build_resume_from_scratch_with_gemini(user_data)

        if not build_data or not build_data.get('rewritten_resume'):
            messages.error(request, "Failed to generate resume. Please try again.")
            return redirect('resume_builder')

        # Create dummy Resume and AnalysisResult so we can use the same templates
        from django.core.files.base import ContentFile
        resume = Resume(
            name=user_data['name'],
            email=user_data['email'],
            phone=user_data['phone'],
            raw_text="[Generated by AI Builder]"
        )
        # Give it a dummy file
        resume.file.save(f"{user_data['name'].replace(' ', '_')}_ai.txt", ContentFile(b"AI Builder Record"))
        
        result = AnalysisResult.objects.create(
            resume=resume,
            job_description=f"Target Role: {user_data['job_title']} in {user_data['sector']}",
            ats_score=100,  # Auto-perfect score for AI generated
            rewritten_resume=build_data['rewritten_resume'],
            resume_skills=build_data.get('skills', []),
            improvement_notes=build_data.get('improvement_notes', []),
            active_ai_model=build_data.get('active_model', 'Gemini')
        )
        
        messages.success(request, "Your AI Resume has been successfully built!")
        return redirect('generate_resume', pk=result.pk)

    return render(request, 'core/resume_builder.html', {'gemini_available': is_gemini_available()})


# ---------------------------------------------------------------------------
# API: Submit AI Feedback
# ---------------------------------------------------------------------------
@require_POST
def submit_feedback(request):
    """API endpoint to record user feedback on AI suggestions."""
    try:
        data = json.loads(request.body)
        suggestion_text = data.get('suggestion_text')
        action_taken = data.get('action_taken')
        
        if suggestion_text and action_taken in ['like', 'apply']:
            from .models import AIFeedback
            AIFeedback.objects.create(
                suggestion_text=suggestion_text,
                action_taken=action_taken
            )
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ---------------------------------------------------------------------------
# API: Sri AI Chat
# ---------------------------------------------------------------------------
@require_POST
def sri_ai_chat(request):
    """API endpoint to process interactive chat messages."""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        
        if not message:
            return JsonResponse({'reply': 'Please provide a message.'}, status=400)
            
        from .gemini_service import chat_with_sri_ai
        reply = chat_with_sri_ai(message)
        
        return JsonResponse({'reply': reply})
    except Exception as e:
        return JsonResponse({'reply': f'An error occurred: {str(e)}'}, status=500)

# ---------------------------------------------------------------------------
# API: Upload Resume Photo
# ---------------------------------------------------------------------------
@require_POST
def upload_resume_photo(request, pk):
    """API endpoint to upload a profile picture for a specific resume."""
    try:
        resume = get_object_or_404(Resume, pk=pk)
        if 'profile_picture' in request.FILES:
            resume.profile_picture = request.FILES['profile_picture']
            resume.save()
            return JsonResponse({'status': 'success', 'url': resume.profile_picture.url})
        return JsonResponse({'status': 'error', 'message': 'No file provided'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
