/* ============================================================
   ResumeXpert – main.js
   All client-side interactivity
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  // ── 1. Drag-and-drop file upload ──────────────────────────────────────
  const dropzone  = document.getElementById('dropzone');
  const fileInput = document.getElementById('resumeFile');
  const fileInfo  = document.getElementById('fileInfo');
  const fileName  = document.getElementById('fileName');
  const fileSize  = document.getElementById('fileSize');

  if (dropzone && fileInput) {

    // Click on dropzone triggers file picker
    dropzone.addEventListener('click', function (e) {
      if (e.target !== fileInput) fileInput.click();
    });

    ['dragenter', 'dragover'].forEach(ev => {
      dropzone.addEventListener(ev, function (e) {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(ev => {
      dropzone.addEventListener(ev, function (e) {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', function (e) {
      const dt    = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        fileInput.files = files;
        showFileInfo(files[0]);
      }
    });

    fileInput.addEventListener('change', function () {
      if (this.files && this.files.length > 0) {
        showFileInfo(this.files[0]);
      }
    });

    function showFileInfo(file) {
      if (!fileInfo || !fileName || !fileSize) return;
      const allowed = ['.pdf', '.docx'];
      const ext     = '.' + file.name.split('.').pop().toLowerCase();
      
      if (!allowed.includes(ext)) {
        alert('Only PDF and DOCX files are allowed.');
        fileInput.value = '';
        return;
      }
      
      // Strict 2MB Limit (Client-Side Validation)
      if (file.size > 2 * 1024 * 1024) {
        alert('File size too large. This is a beta version with a 2MB limit.');
        fileInput.value = '';
        return;
      }

      fileName.textContent = file.name;
      fileSize.textContent = formatBytes(file.size);
      fileInfo.classList.remove('d-none');
    }

    function formatBytes(bytes) {
      if (bytes < 1024)        return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }
  }

  // ── 2. Submit button loading state ───────────────────────────────────
  const uploadForm = document.getElementById('uploadForm');
  const submitBtn  = document.getElementById('submitBtn');

  if (uploadForm && submitBtn) {
    uploadForm.addEventListener('submit', function () {
      const text    = submitBtn.querySelector('.btn-text');
      const loading = submitBtn.querySelector('.btn-loading');
      if (text)    text.classList.add('d-none');
      if (loading) loading.classList.remove('d-none');
      submitBtn.disabled = true;
    });
  }

  // ── 3. JD character counter ───────────────────────────────────────────
  const jdTextarea = document.querySelector('textarea[name="job_description"]');
  if (jdTextarea) {
    const counter = document.createElement('div');
    counter.className = 'form-text text-end mt-1';
    jdTextarea.parentNode.appendChild(counter);

    function updateCounter() {
      const count = jdTextarea.value.length;
      const color = count < 30 ? 'text-danger' : 'text-muted';
      counter.className = `form-text text-end mt-1 ${color}`;
      counter.textContent = count + ' characters';
    }

    jdTextarea.addEventListener('input', updateCounter);
    updateCounter();
  }

  // ── 4. Smooth scroll-in animations (Intersection Observer) ───────────
  const cards = document.querySelectorAll('.rx-card, .rx-suggestion-card, .rx-question-card');

  if ('IntersectionObserver' in window && cards.length) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('rx-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });

    // Add base animation style inline so no extra CSS file needed
    const styleTag = document.createElement('style');
    styleTag.textContent = `
      .rx-card, .rx-suggestion-card, .rx-question-card {
        opacity: 0;
        transform: translateY(16px);
        transition: opacity 0.4s ease, transform 0.4s ease;
      }
      .rx-visible {
        opacity: 1 !important;
        transform: translateY(0) !important;
      }
    `;
    document.head.appendChild(styleTag);

    cards.forEach(c => observer.observe(c));
  }

  // ── 5. Exam: keyboard shortcuts (1-4 keys select option) ─────────────
  const examForm = document.getElementById('examForm');
  if (examForm) {
    // Highlight selected option label
    document.querySelectorAll('.rx-option-radio').forEach(function (radio) {
      radio.addEventListener('change', function () {
        // Reset siblings in same group
        const name = this.name;
        document.querySelectorAll(`input[name="${name}"]`).forEach(function (r) {
          r.closest('.rx-option-label').style.borderColor = '';
          r.closest('.rx-option-label').style.background  = '';
        });
        // Highlight chosen
        const lbl = this.closest('.rx-option-label');
        if (lbl) {
          lbl.style.borderColor = 'var(--rx-primary)';
          lbl.style.background  = 'var(--rx-primary-light)';
        }
      });
    });
  }

  // ── 6. Tooltips (Bootstrap) ───────────────────────────────────────────
  const tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  if (tooltipEls.length && typeof bootstrap !== 'undefined') {
    tooltipEls.forEach(el => new bootstrap.Tooltip(el));
  }

  // ── 7. Auto-dismiss alerts after 5 s ─────────────────────────────────
  document.querySelectorAll('.alert.alert-dismissible').forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert && bootstrap.Alert.getOrCreateInstance
        ? bootstrap.Alert.getOrCreateInstance(alert)
        : null;
      if (bsAlert) bsAlert.close();
      else alert.remove();
    }, 5000);
  });

});
