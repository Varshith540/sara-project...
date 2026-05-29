/**
 * upload_controller.js — ResumeXpert Upload Orchestrator
 * =======================================================
 * Manages the full client-side upload pipeline:
 *  1. Spawns resume_worker.js when a file is selected
 *  2. Consumes worker progress/result messages
 *  3. Builds a FormData payload (extracted text OR compressed image)
 *  4. Submits via Fetch to the NDJSON streaming endpoint
 *  5. Drives the multi-phase progress UI
 *
 * Relies on:
 *  - DOM elements rendered by upload.html
 *  - WORKER_URL / PDF_WORKER_URL globals injected by upload.html
 */

(function () {
  'use strict';

  // ── Constants ───────────────────────────────────────────────────────────────
  const ALLOWED       = ['.pdf', '.docx', '.jpg', '.jpeg', '.png'];
  const IMAGE_TYPES   = ['.jpg', '.jpeg', '.png'];
  const MAX_SIZE_BYTES = 50 * 1024 * 1024;   // 50 MB hard limit

  // PDF.js CDN worker URL (injected by template into window.PDF_WORKER_URL)
  const PDF_WORKER_URL = window.PDF_WORKER_URL ||
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  // Static URL of our Web Worker (injected by template into window.RESUME_WORKER_URL)
  const RESUME_WORKER_URL = window.RESUME_WORKER_URL || '/static/js/resume_worker.js';

  // ── DOM refs ─────────────────────────────────────────────────────────────────
  const fileInput       = document.getElementById('resumeFile');
  const jdInput         = document.getElementById('id_job_description');
  const submitBtn       = document.getElementById('submitBtn');
  const dropzone        = document.getElementById('dropzone');
  const filePreviewCard = document.getElementById('filePreviewCard');
  const removeFileBtn   = document.getElementById('removeFileBtn');
  const fileError       = document.getElementById('fileError');
  const reSelectBanner  = document.getElementById('reSelectBanner');
  const previewBadge    = document.getElementById('previewBadge');
  const previewIconBox  = document.getElementById('previewIconBox');
  const previewThumb    = document.getElementById('previewThumb');
  const previewFileIcon = document.getElementById('previewFileIcon');
  const workerBar       = document.getElementById('workerProgressBar');
  const workerBarWrap   = document.getElementById('workerProgressWrap');
  const workerBarMsg    = document.getElementById('workerProgressMsg');
  const clientExtText   = document.getElementById('client_extracted_text');
  const clientFileType  = document.getElementById('client_file_type');

  // ── State ────────────────────────────────────────────────────────────────────
  let _pickerOpen    = false;
  let _worker        = null;
  let _workerResult  = null;   // populated once worker finishes
  let _compressedFile = null;  // Blob from worker (for images)

  // ── Utility ──────────────────────────────────────────────────────────────────
  function formatBytes(bytes, decimals = 1) {
    if (!+bytes) return '0 Bytes';
    const k = 1024, sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
  }

  function getFileExt(name) {
    const idx = name.lastIndexOf('.');
    return idx >= 0 ? name.slice(idx).toLowerCase() : '';
  }

  function showErrorToast(msg) {
    document.getElementById('fileErrorText').textContent = msg;
    fileError.classList.remove('d-none');
    fileError.classList.add('rx-error-toast-in');
  }

  function hideErrorToast() {
    fileError.classList.add('d-none');
    fileError.classList.remove('rx-error-toast-in');
  }

  function validateForm() {
    const hasFile = (fileInput && fileInput.files && fileInput.files.length > 0) || !!_workerResult;
    const hasJD   = jdInput && jdInput.value.trim().length >= 30;
    submitBtn.disabled = !(hasFile && hasJD);
  }

  // ── Worker progress bar ───────────────────────────────────────────────────────
  function showWorkerProgress(msg, pct) {
    if (!workerBarWrap) return;
    workerBarWrap.classList.remove('d-none');
    if (workerBarMsg) workerBarMsg.textContent = msg;
    if (workerBar)    workerBar.style.width = `${pct}%`;
  }

  function hideWorkerProgress() {
    if (workerBarWrap) workerBarWrap.classList.add('d-none');
    if (workerBar)     workerBar.style.width = '0%';
  }

  // ── Preview card ──────────────────────────────────────────────────────────────
  function showPreviewCard(name, sizeText, reSelect, isImage, thumbUrl) {
    document.getElementById('previewFileName').textContent = name;
    document.getElementById('previewFileSize').textContent = sizeText;

    if (isImage && thumbUrl) {
      previewIconBox.style.display = 'none';
      previewThumb.src = thumbUrl;
      previewThumb.style.display = 'block';
    } else {
      previewThumb.style.display = 'none';
      previewIconBox.style.display = '';
      const ext = getFileExt(name);
      previewFileIcon.className = ext === '.pdf'
        ? 'bi bi-file-earmark-pdf-fill'
        : ext === '.docx'
          ? 'bi bi-file-earmark-word-fill'
          : 'bi bi-image-fill';
    }

    if (reSelect) {
      previewBadge.className = 'badge bg-warning text-dark';
      previewBadge.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Re-select file below';
    } else {
      previewBadge.className = isImage ? 'badge bg-info' : 'badge bg-success';
      previewBadge.innerHTML = isImage
        ? '<i class="bi bi-eye me-1"></i>Vision AI will analyse'
        : '<i class="bi bi-check-circle me-1"></i>Ready to Analyse';
    }

    dropzone.classList.add('d-none');
    filePreviewCard.classList.remove('d-none');
    filePreviewCard.classList.add('d-flex');
  }

  function resetFileUI() {
    _terminateWorker();
    _workerResult   = null;
    _compressedFile = null;

    if (fileInput)    fileInput.value = '';
    if (clientExtText)  clientExtText.value  = '';
    if (clientFileType) clientFileType.value  = '';

    filePreviewCard.classList.add('d-none');
    filePreviewCard.classList.remove('d-flex');
    dropzone.classList.remove('d-none');
    hideErrorToast();
    hideWorkerProgress();
    reSelectBanner.classList.add('d-none');
    previewThumb.style.display = 'none';
    previewThumb.src = '';
    previewIconBox.style.display = '';
    sessionStorage.removeItem('rx_pending_file');
    validateForm();
  }

  // ── Web Worker lifecycle ──────────────────────────────────────────────────────
  function _terminateWorker() {
    if (_worker) { _worker.terminate(); _worker = null; }
  }

  function _spawnWorker(file) {
    _terminateWorker();
    _workerResult   = null;
    _compressedFile = null;
    if (clientExtText)  clientExtText.value  = '';
    if (clientFileType) clientFileType.value  = '';

    const ext     = getFileExt(file.name);
    const isImage = IMAGE_TYPES.includes(ext);
    const isPdf   = ext === '.pdf';

    // DOCX → no worker, server handles it
    if (!isImage && !isPdf) return;

    try {
      _worker = new Worker(RESUME_WORKER_URL);
    } catch (e) {
      console.warn('[UploadController] Web Worker unavailable:', e);
      return;
    }

    showWorkerProgress('Preparing file...', 5);

    _worker.onmessage = function (e) {
      const { type, step, msg, payload } = e.data;

      if (type === 'progress') {
        const pctMap = { worker_start: 20, worker_reading: 50, worker_compress: 60 };
        showWorkerProgress(msg, pctMap[step] || 30);
        return;
      }

      if (type === 'error') {
        console.warn('[Worker]', msg);
        hideWorkerProgress();
        _terminateWorker();
        showErrorToast(`Processing failed: ${msg || 'Unknown worker error. Please try again.'}`);
        return;
      }

      if (type === 'result') {
        _workerResult = payload;
        _terminateWorker();

        if (payload.mode === 'text') {
          // PDF text extracted — store in hidden field
          if (clientExtText)  clientExtText.value  = payload.extractedText;
          if (clientFileType) clientFileType.value  = 'pdf_text';

          const saving = payload.originalSize - payload.finalSize;
          showWorkerProgress(
            `✅ Text extracted! Saved ~${formatBytes(saving)} of upload data.`,
            100
          );
          // Update badge
          previewBadge.className = 'badge bg-success';
          previewBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i>Text Extracted — Ready';

        } else if (payload.mode === 'compressed_image') {
          _compressedFile = payload.compressedBlob;
          if (clientFileType) clientFileType.value = 'compressed_image';

          const saving = payload.originalSize - payload.finalSize;
          showWorkerProgress(
            `✅ Compressed! ${formatBytes(payload.originalSize)} → ${formatBytes(payload.finalSize)} (saved ${formatBytes(saving)})`,
            100
          );
          previewBadge.className = 'badge bg-info';
          previewBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i>Compressed — Ready';

        } else if (payload.mode === 'image_pdf') {
          // Scanned PDF — server will use Vision AI
          if (clientFileType) clientFileType.value = 'image_pdf';
          showWorkerProgress('Scanned PDF detected — Vision AI will handle it.', 100);

        } else {
          // fallback — send raw file as usual
          hideWorkerProgress();
        }

        validateForm();
      }
    };

    _worker.onerror = function (err) {
      console.error('[Worker error]', err);
      hideWorkerProgress();
      _terminateWorker();
      showErrorToast(
        `Worker failed to load: ${err.message || err.filename || 'Could not start the PDF processor. Your file will be sent to the server for processing.'}`
      );
    };

    // Dispatch to worker
    if (isImage) {
      _worker.postMessage({ op: 'process_image', file });
    } else {
      _worker.postMessage({ op: 'process_pdf', file, pdfJsWorkerSrc: PDF_WORKER_URL });
    }
  }

  // ── Dropzone interactions ─────────────────────────────────────────────────────
  if (dropzone && fileInput) {
    dropzone.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (_pickerOpen) return;
      _pickerOpen = true;
      fileInput.click();
      setTimeout(() => { _pickerOpen = false; }, 1200);
    });

    dropzone.addEventListener('dragover', function (e) {
      e.preventDefault();
      dropzone.classList.add('rx-dropzone-active');
    });
    dropzone.addEventListener('dragleave', function () {
      dropzone.classList.remove('rx-dropzone-active');
    });
    dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      dropzone.classList.remove('rx-dropzone-active');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const dt = new DataTransfer();
        dt.items.add(e.dataTransfer.files[0]);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change'));
      }
    });
  }

  // ── File input change ─────────────────────────────────────────────────────────
  if (fileInput) {
    fileInput.addEventListener('change', function (e) {
      e.stopPropagation();
      _pickerOpen = false;
      hideErrorToast();
      reSelectBanner.classList.add('d-none');

      if (this.files && this.files[0]) {
        const file    = this.files[0];
        const ext     = getFileExt(file.name);
        const isImage = IMAGE_TYPES.includes(ext);

        if (!ALLOWED.includes(ext)) {
          showErrorToast('Invalid format. Supported: PDF, DOCX, JPG, PNG.');
          resetFileUI(); return;
        }
        if (file.size > MAX_SIZE_BYTES) {
          showErrorToast('File too large — max 50 MB.');
          resetFileUI(); return;
        }

        const sizeText = formatBytes(file.size);
        sessionStorage.setItem('rx_pending_file', JSON.stringify({ name: file.name, size: sizeText }));

        const thumbUrl = isImage ? URL.createObjectURL(file) : null;
        showPreviewCard(file.name, sizeText, false, isImage, thumbUrl);
        validateForm();

        // Kick off background processing while user fills the JD
        _spawnWorker(file);
      }
    });
  }

  // ── Remove file ───────────────────────────────────────────────────────────────
  if (removeFileBtn) removeFileBtn.addEventListener('click', resetFileUI);

  // ── JD validation ─────────────────────────────────────────────────────────────
  if (jdInput) jdInput.addEventListener('input', validateForm);

  // ── Page-load restore (after failed POST) ─────────────────────────────────────
  const _hasErrors = document.getElementById('rx-form-error-flag')?.dataset.hasErrors === 'true';
  if (_hasErrors) {
    const saved = sessionStorage.getItem('rx_pending_file');
    if (saved) {
      try {
        const { name, size } = JSON.parse(saved);
        const isImg = IMAGE_TYPES.some(e => name.toLowerCase().endsWith(e));
        showPreviewCard(name, size, true, isImg, null);
        reSelectBanner.classList.remove('d-none');
      } catch (_) { /* ignore */ }
    }
  } else {
    sessionStorage.removeItem('rx_pending_file');
  }

  // ── Form submit ───────────────────────────────────────────────────────────────
  const uploadForm = document.getElementById('uploadForm');
  if (uploadForm) {
    uploadForm.addEventListener('submit', function (e) {
      e.preventDefault();
      _terminateWorker();

      const file = fileInput && fileInput.files && fileInput.files[0];
      if (!file) {
        showErrorToast('Please select a resume file before submitting.');
        dropzone.classList.remove('d-none');
        filePreviewCard.classList.add('d-none');
        return;
      }

      // ── Build FormData ──────────────────────────────────────────────────
      const fd    = new FormData(uploadForm);
      const mode  = clientFileType ? clientFileType.value : '';

      // Forcefully ensure the file is in FormData (fixes ghost uploads)
      if (file) {
        fd.delete('resume_file');
        if (mode === 'compressed_image' && _compressedFile) {
          fd.append('resume_file', _compressedFile, file.name.replace(/\.[^.]+$/, '_compressed.jpg'));
        } else {
          fd.append('resume_file', file);
        }
      }
      
      // For 'pdf_text', client_extracted_text is already in the form as a hidden field.
      // For 'image_pdf' and DOCX (mode=''), original file is sent as-is.

      // ── Show phase spinners ─────────────────────────────────────────────
      const btnText      = submitBtn.querySelector('.btn-text');
      const phaseUpload  = document.getElementById('phaseUpload');
      const phaseConvert = document.getElementById('phaseConvert');
      const phaseAnalyse = document.getElementById('phaseAnalyse');

      function showPhase(el) {
        [btnText, phaseUpload, phaseConvert, phaseAnalyse].forEach(p => p && p.classList.add('d-none'));
        if (el) el.classList.remove('d-none');
      }

      const ext = getFileExt(file.name);
      // Skip convert phase if text was pre-extracted; server goes straight to AI
      const needsConvert = (mode !== 'pdf_text') && (IMAGE_TYPES.includes(ext) || ext === '.pdf');

      showPhase(phaseUpload);
      submitBtn.disabled = true;
      hideWorkerProgress();

      if (needsConvert) {
        setTimeout(() => showPhase(phaseConvert), 800);
        setTimeout(() => showPhase(phaseAnalyse), 4000);
      } else {
        setTimeout(() => showPhase(phaseAnalyse), 800);
      }

      sessionStorage.removeItem('rx_pending_file');

      // ── Stream submission ───────────────────────────────────────────────
      fetch(uploadForm.action || window.location.href, {
        method:      'POST',
        body:        fd,
        credentials: 'same-origin',
        headers:     { 'X-Requested-With': 'XMLHttpRequest' },
      }).then(async response => {
        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer    = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop();   // keep incomplete line

          for (const line of lines) {
            if (!line.trim()) continue;
            let event;
            try {
              event = JSON.parse(line);
            } catch (_) {
              continue; // malformed line — ignore
            }
            
            // If the JSON contains an explicit error key, throw it to trigger the catch block
            if (event.error) {
              throw new Error(event.error);
            }
            
            _handleStreamEvent(event, showPhase, phaseAnalyse);
          }
        }
      }).catch(err => {
        showErrorToast(`Upload failed: ${err.message}`);
        submitBtn.disabled = false;
        showPhase(btnText);
      });
    });
  }

  // ── NDJSON stream event handler ───────────────────────────────────────────────
  function _handleStreamEvent(event, showPhase, phaseAnalyse) {
    const { step, msg, redirect } = event;

    if (step === 'success' && redirect) {
      window.location.href = redirect;
      return;
    }
    if (step === 'error') {
      showErrorToast(msg || 'An error occurred.');
      submitBtn.disabled = false;
      document.querySelector('.btn-text')?.classList.remove('d-none');
      [document.getElementById('phaseUpload'), document.getElementById('phaseConvert'), phaseAnalyse]
        .forEach(el => el && el.classList.add('d-none'));
      return;
    }
    if (step === 'large_file_detected') {
      // Prompt user to compress — since we handle this client-side now, this
      // should rarely fire. If it does, just proceed with server compression.
      const fd2 = new FormData(document.getElementById('uploadForm'));
      fd2.set('force_compress', 'true');
      return;
    }
    // For all other steps (validation, ocr, analysis, eta, etc.) just update phase UI
    if (['ocr', 'vision', 'analysis', 'gemini'].some(k => step && step.includes(k))) {
      showPhase(phaseAnalyse);
    }
  }

})();
