"""
ResumeXpert – Views
"""

import json
import os
import gc
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
import core.middleware


# ---------------------------------------------------------------------------
# Home / Upload view
# ---------------------------------------------------------------------------
def upload_resume(request):
    """Show the upload form and process submissions via AJAX or standard POST."""
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

        # ── Pre-emptive Memory Guard ─────────────────────────────────────────
        import psutil
        if psutil.virtual_memory().percent > 80:
            msg = "System Busy"
            if is_ajax:
                return JsonResponse({'status': 'MEM_LIMIT_REACHED', 'message': msg})
            messages.error(request, f"⚠️ {msg}: Memory limit reached. Please try a smaller file or wait.")
            return render(request, 'core/upload.html')

        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_ajax:
                from django.http import StreamingHttpResponse
                return StreamingHttpResponse(
                    _process_upload_stream(request, form),
                    content_type='application/x-ndjson'
                )
            else:
                messages.error(request, 'Please enable JavaScript to upload files.')
                return render(request, 'core/upload.html', {'form': form})
        # Form has errors – re-render
        print("====== GHOST UPLOAD AUDIT ======")
        print(f"request.FILES present: {'resume_file' in request.FILES}")
        print(f"DEBUG: Form Errors -> {form.errors.as_data()}")
        print("================================")
        
        # Intercept Form Validation Error for Sri AI Live Diagnosing
        core.middleware._LATEST_DIAGNOSTIC = {
            "type": "validation_error",
            "message": f"I intercepted a Ghost Upload / Form Validation Error!\n\n**Missing Fields/Errors:** {form.errors.as_json()}\n\nMake sure the HTML form has `enctype=\"multipart/form-data\"` and the input name is correct."
        }

        
        # Give explicit frontend feedback to the user
        error_msgs = []
        for field, errors in form.errors.items():
            for error in errors:
                error_msgs.append(f"{field.replace('_', ' ').title()}: {error}")
                messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
                
        if is_ajax: return JsonResponse({'status': 'error', 'message': " | ".join(error_msgs)})
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
    """View to search and display company analysis using Gemini.

    GET  → renders the page shell (always HTML).
    POST → runs the AI analysis. Returns JsonResponse for AJAX callers;
           falls back to a redirect for non-AJAX (progressive enhancement).
    """
    result = get_object_or_404(AnalysisResult, pk=pk)

    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', '')
        )
        if company_name:
            from .gemini_service import analyze_company_with_gemini
            analysis = analyze_company_with_gemini(company_name, result.job_description)
            if analysis:
                result.company_name     = company_name
                result.company_analysis = analysis
                result.save(update_fields=['company_name', 'company_analysis'])
                if is_ajax:
                    return JsonResponse({'status': 'ok', 'company_name': company_name, 'analysis': analysis})
                messages.success(request, f"Analysis for {company_name} completed!")
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': 'AI could not analyse this company.'}, status=502)
                messages.error(request, "Failed to analyze the company right now.")
        else:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': 'Company name is required.'}, status=400)
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

# ---------------------------------------------------------------------------
# Generator: Upload Stream Pipeline
# ---------------------------------------------------------------------------
def _process_upload_stream(request, form):
    """Generator yielding NDJSON milestones for the AJAX stream."""
    import json
    import os
    import gc
    from .models import Resume, AnalysisResult
    from .resume_parser import extract_text, extract_email, extract_phone, extract_name
    from .scoring_engine import calculate_score
    from .gemini_service import analyze_resume_image_with_gemini, analyze_resume_with_gemini

    def send_status(step, msg):
        return json.dumps({'step': step, 'msg': msg}) + '\n'

    def send_error(msg):
        return json.dumps({'step': 'error', 'msg': msg}) + '\n'

    temp_files = []

    try:
        job_description = form.cleaned_data['job_description']
        manual_name     = form.cleaned_data.get('full_name', '').strip()
        force_compress  = request.POST.get('force_compress') == 'true'

        # ── Client-side pre-processing bypass ───────────────────────────────
        # If the browser's Web Worker already extracted PDF text or compressed
        # an image, the controller posts these fields so the server skips the
        # expensive PyMuPDF / Pillow / pdfplumber passes entirely.
        client_text      = request.POST.get('client_extracted_text', '').strip()
        client_file_type = request.POST.get('client_file_type', '')   # 'pdf_text' | 'compressed_image' | 'image_pdf' | ''

        edge_images = request.POST.getlist('edge_processed_images[]')

        if edge_images:
            uploaded_file = None
            is_image = True
            file_ext = '.jpg'
            file_size = sum(len(img) for img in edge_images)
        else:
            uploaded_file   = request.FILES.get('resume_file')
            if not uploaded_file:
                yield send_error("⚠️ No file or edge data provided.")
                return
            file_ext        = os.path.splitext(uploaded_file.name)[1].lower()
            is_image        = file_ext in ('.jpg', '.jpeg', '.png') or client_file_type == 'compressed_image'
            file_size       = uploaded_file.size


        yield send_status('validation', "File Received. Starting Validation...")

        if file_size > 30 * 1024 * 1024:
            yield send_error("⚠️ File size too large. This is a beta version with a 30MB capacity limit.")
            return

        # ── Dynamic ETA Logic (client-aware) ────────────────────────────────
        # If the browser pre-extracted text, we skip server OCR → shorter ETA.
        eta_seconds = 25
        if client_text:
            eta_seconds = 10
        elif is_image or file_ext == '.pdf':
            if file_size > 10 * 1024 * 1024:
                eta_seconds = 150
            elif is_image or (file_size > 2 * 1024 * 1024):
                eta_seconds = 75
        yield json.dumps({"step": "eta", "seconds": eta_seconds}) + '\n'



        if uploaded_file:
            yield send_status('compression', "Applying zlib in-memory chunk streaming...")
            import zlib
            import io
            import tempfile
            from django.core.files import File
            
            # Compress dynamically in memory
            compressed_buffer = io.BytesIO()
            compressor = zlib.compressobj(level=zlib.Z_BEST_COMPRESSION)
            
            for chunk in uploaded_file.chunks(chunk_size=65536):
                compressed_buffer.write(compressor.compress(chunk))
            compressed_buffer.write(compressor.flush())
            
            # Decompress into a temporary file to keep RAM usage minimal
            compressed_buffer.seek(0)
            decompressor = zlib.decompressobj()
            
            resume = Resume()
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                while True:
                    c_chunk = compressed_buffer.read(65536)
                    if not c_chunk:
                        break
                    tmp.write(decompressor.decompress(c_chunk))
                tmp.write(decompressor.flush())
                tmp_path = tmp.name
                
            with open(tmp_path, 'rb') as f:
                resume.file.save(uploaded_file.name, File(f), save=True)
                
            os.remove(tmp_path)
            file_path = resume.file.path

        else:
            import base64
            from django.core.files.base import ContentFile
            # Decode the first edge-processed image to satisfy the DB FileField
            img_data = base64.b64decode(edge_images[0].split(',')[1])
            resume = Resume()
            resume.file.save('edge_processed.jpg', ContentFile(img_data), save=True)
            file_path = resume.file.path
            
        temp_files.append(file_path)

        # ── Adaptive Compression (> 5MB) ─────────────────────────────────────
        if file_size > 5 * 1024 * 1024:
            yield send_status('compression', "RAM usage high... Triggering adaptive compression to save server.")
            try:
                if not is_image and file_ext == '.pdf':
                    import fitz
                    compressed_path = file_path + ".compressed.pdf"
                    temp_files.append(compressed_path)
                    with fitz.open(file_path) as doc:
                        doc.save(compressed_path, garbage=4, deflate=True, clean=True)
                    os.replace(compressed_path, file_path)
                    print(f"[Compression] PDF compressed successfully: {file_path}")
                elif is_image:
                    from PIL import Image
                    compressed_path = file_path + ".compressed.jpg"
                    temp_files.append(compressed_path)
                    with Image.open(file_path) as img:
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                        img.save(compressed_path, "JPEG", quality=60, optimize=True)
                    os.replace(compressed_path, file_path)
                    print(f"[Compression] Image compressed successfully: {file_path}")
            except Exception as e:
                print(f"[Compression] Compression failed, proceeding with original. Error: {e}")
            gc.collect()

        # ── Extraction & AI Analysis ──────────────────────────────────────────
        if client_text and client_file_type == 'pdf_text':
            # Fast path: browser already extracted text — skip server OCR entirely
            yield send_status('ocr', "Using pre-extracted text from browser...")
            raw_text = client_text
            try:
                gemini_data = {}
                for update in analyze_resume_with_gemini(raw_text, job_description):
                    if isinstance(update, dict) and 'step' in update:
                        yield send_status(update['step'], update['msg'])
                    elif isinstance(update, dict):
                        gemini_data = update
                gc.collect()
            except Exception as e:
                resume.delete()
                msg = str(e)
                if '429' in msg:
                    yield json.dumps({'step': 'MEM_LIMIT_REACHED', 'msg': 'Rate limit exceeded'}) + '\n'
                    return
                yield send_error(f"Analysis failed: {msg[:100]}")
                return

        elif is_image:
            try:
                vision_data = {}
                for update in analyze_resume_image_with_gemini(file_path, job_description, edge_images=edge_images):
                    if isinstance(update, dict) and 'step' in update:
                        yield send_status(update['step'], update['msg'])
                    elif isinstance(update, dict):
                        vision_data = update
                gc.collect()
            except TimeoutError as te:
                resume.delete()
                yield send_error(f"⏱️ Connection Timeout: {te}")
                return
            if not vision_data:
                resume.delete()
                yield send_error("⚠️ Vision AI could not analyse your resume image. Please ensure it's clear.")
                return

            raw_text    = vision_data.pop('ocr_text', '') or '[Image resume — text extracted by Vision AI]'
            gemini_data = vision_data
        else:
            yield send_status('ocr', "Sri AI is reading the content...")
            from .resume_parser import IMAGE_FILE_SENTINEL
            raw_text = extract_text(file_path)

            if raw_text == IMAGE_FILE_SENTINEL:
                raw_text = ''

            if not raw_text and file_ext == '.pdf':
                resume.delete()
                yield send_error("We couldn't read this PDF text. Please try a smaller or text-based PDF.")
                return

            elif not raw_text:
                resume.delete()
                yield send_error("⚠️ Scanning failed. Please ensure the file is not password-protected or corrupted.")
                return

            else:
                try:
                    gemini_data = {}
                    for update in analyze_resume_with_gemini(raw_text, job_description):
                        if isinstance(update, dict) and 'step' in update:
                            yield send_status(update['step'], update['msg'])
                        elif isinstance(update, dict):
                            gemini_data = update
                    gc.collect()
                except Exception as e:
                    resume.delete()
                    msg = str(e)
                    if '429' in msg:
                        yield json.dumps({'step': 'MEM_LIMIT_REACHED', 'msg': 'Rate limit exceeded'}) + '\n'
                        return
                    yield send_error(f"Analysis failed: {msg[:100]}")
                    return

        # ── Finalizing Data ──────────────────────────────────────────────────
        yield send_status('analysis', "Finalizing ATS score & Suggestions...")
        
        resume.raw_text        = raw_text
        resume.name            = manual_name or extract_name(raw_text)
        resume.email           = extract_email(raw_text)
        resume.phone           = extract_phone(raw_text)
        resume.target_industry = form.cleaned_data.get('target_industry', '').strip()
        resume.save()
        
        from .resume_parser import extract_structured_data
        yield send_status('structuring', "Building structured JSON data...")
        structured_data = extract_structured_data(raw_text)

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
            ai_summary        = gemini_data.get('ai_summary', ''),
            ai_suggestions    = gemini_data.get('ai_suggestions', []),
            interview_questions = gemini_data.get('interview_questions', []),
            job_fit_score     = gemini_data.get('job_fit_score', 0),
            active_ai_model   = gemini_data.get('active_model', 'Gemini'),
            structured_data   = structured_data,
        )
        result.save()

        gc.collect()
        yield json.dumps({'step': 'success', 'redirect': f'/dashboard/{result.pk}/'}) + '\n'

    except Exception as e:
        print(f"[Upload Stream Error] {e}")
        yield send_error(f"Server Error: {str(e)[:100]}")
    finally:
        # Cleanup temporary processing files
        for tmp_file in temp_files:
            if ".compressed." in tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
        gc.collect()

# ---------------------------------------------------------------------------
# API: Resume Comparison Engine
# ---------------------------------------------------------------------------
from django.views.decorators.csrf import csrf_exempt
from django.http import StreamingHttpResponse

@csrf_exempt
def compare_resumes(request):
    """
    API endpoint to compare two resumes against a JD.
    Expects POST with 'resume1', 'resume2' texts and 'job_description'.
    Returns NDJSON stream.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    resume1_text = request.POST.get('resume1', '').strip()
    resume2_text = request.POST.get('resume2', '').strip()
    jd = request.POST.get('job_description', '').strip()

    if not resume1_text or not resume2_text or not jd:
        return JsonResponse({'error': 'Missing resume1, resume2, or job_description'}, status=400)

    def _compare_stream():
        yield json.dumps({"step": "init", "msg": "Sri AI is initializing Enterprise Compare Engine..."}) + '\n'
        from .gemini_service import compare_resumes_with_gemini
        
        match_matrix = None
        for update in compare_resumes_with_gemini(resume1_text, resume2_text, jd):
            if isinstance(update, dict) and 'step' in update:
                yield json.dumps(update) + '\n'
            elif isinstance(update, dict):
                match_matrix = update
        
        if match_matrix:
            yield json.dumps({"step": "success", "data": match_matrix}) + '\n'
        else:
            yield json.dumps({"step": "error", "msg": "Failed to generate Match Matrix."}) + '\n'

    return StreamingHttpResponse(_compare_stream(), content_type='application/x-ndjson')

# ---------------------------------------------------------------------------
# Deep Health Check Endpoint (used by Phoenix Protocol CI/CD)
# ---------------------------------------------------------------------------
def deep_health_check(request):
    """
    Comprehensive health probe for CI/CD and load-balancer checks.
    Returns HTTP 200 only when DB connectivity and critical env vars are OK.
    Returns HTTP 503 with a JSON body describing which checks failed.
    """
    import time
    from django.db import connection, OperationalError

    checks = {}
    overall_ok = True

    # 1. Database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except OperationalError as e:
        checks["database"] = f"FAIL: {e}"
        overall_ok = False

    # 2. Safe Mode sentinel (memory pressure flag from wsgi.py monitor)
    safe_mode_active = os.path.exists('/tmp/SAFE_MODE.lock')
    checks["safe_mode"] = "engaged" if safe_mode_active else "ok"
    # Safe mode is informational only — does not fail the health check

    # 3. Critical environment variables
    for key in ["GEMINI_API_KEY", "SECRET_KEY"]:
        present = bool(os.environ.get(key, '').strip())
        checks[f"env_{key.lower()}"] = "set" if present else "MISSING"
        if not present:
            overall_ok = False

    http_status = 200 if overall_ok else 503
    return JsonResponse(
        {
            "status": "healthy" if overall_ok else "unhealthy",
            "checks": checks,
            "timestamp": time.time(),
        },
        status=http_status,
    )

# ---------------------------------------------------------------------------
# API: Chat Diagnostics for Sri AI Chat UI
# ---------------------------------------------------------------------------
def chat_diagnostics(request):
    """Returns the latest backend error / diagnostic for Sri AI UI."""
    diagnostic = core.middleware.get_latest_diagnostic()
    if diagnostic:
        core.middleware.clear_diagnostic()
        return JsonResponse({"has_error": True, "diagnostic": diagnostic})
    return JsonResponse({"has_error": False})

# ---------------------------------------------------------------------------
# Heartbeat Endpoint (System Reliability Guardian)
# ---------------------------------------------------------------------------
def ping_alive(request):
    """
    Ultra-lightweight endpoint to keep the Render server awake.
    Does not touch the DB or AI models.
    """
    return JsonResponse({"status": "alive"})

# ---------------------------------------------------------------------------
# Sri AI CI/CD One-Click Webhook
# ---------------------------------------------------------------------------
def sri_approve_deployment(request, token):
    """
    Webhook endpoint to trigger the One-Click Deployment pipeline.
    Expects a PR number parameter in the query string, e.g., ?pr=4
    """
    pr_number = request.GET.get('pr')
    if not pr_number:
        return JsonResponse({"error": "Missing PR number parameter"}, status=400)
        
    from .models import PendingDeployment
    try:
        deployment = PendingDeployment.objects.get(pr_number=pr_number, status='pending')
    except PendingDeployment.DoesNotExist:
        return HttpResponse("<h1>Deployment is no longer pending or does not exist.</h1>", status=400)
        
    from .sri_cicd import execute_cicd_pipeline
    result = execute_cicd_pipeline(pr_number, reason_log=deployment.analysis_log)
    
    if result.get("status") == "success":
        deployment.status = 'approved'
        deployment.save()
        html = f"""
        <html><body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1 style="color: green;">✅ Deployment Approved & Successful!</h1>
            <p>{result.get('message')}</p>
        </body></html>
        """
    else:
        html = f"""
        <html><body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1 style="color: red;">❌ Deployment Failed. Rolled Back Safely.</h1>
            <p>{result.get('message')}</p>
        </body></html>
        """
        
    from django.http import HttpResponse
    return HttpResponse(html)

def sri_reject_deployment(request, token):
    """
    Webhook endpoint to reject a pending autonomous deployment.
    """
    pr_number = request.GET.get('pr')
    if not pr_number:
        return JsonResponse({"error": "Missing PR number parameter"}, status=400)
        
    from .models import PendingDeployment
    try:
        deployment = PendingDeployment.objects.get(pr_number=pr_number, status='pending')
    except PendingDeployment.DoesNotExist:
        from django.http import HttpResponse
        return HttpResponse("<h1>Deployment is no longer pending or does not exist.</h1>", status=400)
        
    from .sri_cicd import execute_reject_pipeline
    result = execute_reject_pipeline(pr_number)
    
    if result.get("status") == "success":
        deployment.status = 'rejected'
        deployment.save()
        html = f"""
        <html><body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1 style="color: #d9534f;">🛑 Deployment Rejected & Discarded</h1>
            <p>The isolated update branch has been safely deleted. The AI will not proceed.</p>
        </body></html>
        """
    else:
        html = f"""
        <html><body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1 style="color: red;">❌ Error Rejecting Deployment</h1>
            <p>{result.get('message')}</p>
        </body></html>
        """
        
    from django.http import HttpResponse
    return HttpResponse(html)

# ---------------------------------------------------------------------------
# Interactive Mock Interview
# ---------------------------------------------------------------------------
def mock_interview(request, pk):
    """
    Renders the Mock Interview UI and passes the generated interview questions.
    """
    result = get_object_or_404(AnalysisResult, pk=pk)
    questions = result.interview_questions
    
    if not questions:
        messages.warning(request, "No interview questions found. Please ensure Gemini API is configured and re-analyze your resume.")
        return redirect('dashboard', pk=pk)
        
    context = {
        'result': result,
        'questions': questions
    }
    return render(request, 'core/mock_interview.html', context)

@require_POST
def api_evaluate_answer(request):
    """
    AJAX endpoint to evaluate a spoken answer against a question.
    """
    try:
        import json
        data = json.loads(request.body)
        question = data.get('question', '')
        answer = data.get('answer', '')
        
        if not question or not answer:
            return JsonResponse({"error": "Missing question or answer data"}, status=400)
            
        from .interview_evaluator import evaluate_interview_answer
        result = evaluate_interview_answer(question, answer)
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
