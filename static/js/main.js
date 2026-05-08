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
      
      // Optimized 30MB Limit (Client-Side Validation for Render Free Tier)
      if (file.size > 30 * 1024 * 1024) {
        alert('File size too large. This is a beta version with a 30MB capacity limit to ensure stability. Please compress your file.');
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

  // ── 2. Submit button & AJAX Form Upload ────────────────────────────────
  const uploadForm = document.getElementById('uploadForm');
  const submitBtn  = document.getElementById('submitBtn');

  if (uploadForm && submitBtn) {
    uploadForm.addEventListener('submit', function (e) {
      e.preventDefault(); // Intercept standard submission

      const text    = submitBtn.querySelector('.btn-text');
      const loading = submitBtn.querySelector('.btn-loading');
      if (text)    text.classList.add('d-none');
      if (loading) {
          loading.classList.remove('d-none');
          // Sri AI memory optimization feedback
          const loadingText = loading.querySelector('span');
          if (loadingText) loadingText.textContent = " Sri AI is optimizing memory...";
      }
      submitBtn.disabled = true;

      const formData = new FormData(uploadForm);
      performUpload(formData, text, loading);
    });

    function performUpload(formData, text, loading) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 120s timeout

      fetch(uploadForm.action || window.location.href, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(async response => {
        clearTimeout(timeoutId);
        if (response.status === 429) {
          throw new Error('MEM_LIMIT_REACHED');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, {stream: true});
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep the last partial line in buffer
          
          for (let line of lines) {
            if (!line.trim()) continue;
            try {
              const data = JSON.parse(line);
              
              if (data.step === 'large_file_detected') {
                showLargeFileModal(data.msg, formData, text, loading);
                return; // Gracefully exit stream
              } else if (data.step && data.step !== 'success' && data.step !== 'error' && data.step !== 'MEM_LIMIT_REACHED') {
                const loadingText = loading.querySelector('span');
                if (loadingText) loadingText.innerHTML = ` <i class="bi bi-hourglass-split"></i> ${data.msg}`;
              } else if (data.step === 'success') {
                window.location.href = data.redirect;
                return;
              } else if (data.step === 'MEM_LIMIT_REACHED') {
                throw new Error('MEM_LIMIT_REACHED');
              } else if (data.step === 'error') {
                throw new Error(data.msg);
              }
            } catch (e) {
              if (e.message === 'MEM_LIMIT_REACHED' || e.message.includes('Error')) throw e;
            }
          }
        }
      })
      .catch(error => {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
          alert("Server is taking longer than usual due to file size. Please check 'History' in a minute.");
        } else if (error.message === 'MEM_LIMIT_REACHED') {
          showBetaModal();
        } else {
          alert('Network or Server Error: ' + error.message);
        }
        resetSubmitBtn(text, loading);
      });
    }

    function showLargeFileModal(message, formData, text, loading) {
      // Remove any existing modal
      const existing = document.getElementById('largeFileModal');
      if (existing) existing.remove();

      const modalHTML = `
      <div class="modal fade" id="largeFileModal" tabindex="-1" aria-hidden="true" data-bs-backdrop="static">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content border-0 shadow-lg">
            <div class="modal-header bg-warning text-dark border-0">
              <h5 class="modal-title"><i class="bi bi-exclamation-triangle-fill me-2"></i>High Capacity Detected</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close" id="cancelUploadIcon"></button>
            </div>
            <div class="modal-body p-4 text-center">
              <i class="bi bi-file-earmark-zip text-warning mb-3" style="font-size: 3rem;"></i>
              <h4>Action Required</h4>
              <p class="text-muted mb-0">High capacity file detected. To save server memory and time, we will compress this. Estimated time: 60-90 seconds.</p>
            </div>
            <div class="modal-footer border-0 justify-content-center">
              <button type="button" class="btn btn-light px-4" data-bs-dismiss="modal" id="cancelUploadBtn">Cancel</button>
              <button type="button" class="btn btn-warning px-4 text-dark fw-bold" id="proceedCompressBtn">Proceed with Compression</button>
            </div>
          </div>
        </div>
      </div>`;
      
      document.body.insertAdjacentHTML('beforeend', modalHTML);
      const modalEl = document.getElementById('largeFileModal');
      const bsModal = new bootstrap.Modal(modalEl);
      bsModal.show();

      document.getElementById('proceedCompressBtn').addEventListener('click', () => {
        bsModal.hide();
        // Reconstruct form data to ensure no fields (like target_industry) are lost
        const freshFormData = new FormData(uploadForm);
        freshFormData.append('force_compress', 'true');
        
        // Reset loader UI
        if (text) text.classList.add('d-none');
        if (loading) {
            loading.classList.remove('d-none');
            const loadingText = loading.querySelector('span');
            if (loadingText) loadingText.innerHTML = ` <i class="bi bi-hourglass-split"></i> Preparing Compression...`;
        }
        performUpload(freshFormData, text, loading);
      });

      const cancelAction = () => {
        resetSubmitBtn(text, loading);
      };
      
      document.getElementById('cancelUploadBtn').addEventListener('click', cancelAction);
      document.getElementById('cancelUploadIcon').addEventListener('click', cancelAction);
    }

    function resetSubmitBtn(text, loading) {
        if (text) text.classList.remove('d-none');
        if (loading) loading.classList.add('d-none');
        submitBtn.disabled = false;
    }

    function showBetaModal() {
        let modalEl = document.getElementById('betaCapacityModal');
        if (!modalEl) {
            const modalHTML = `
            <div class="modal fade" id="betaCapacityModal" tabindex="-1" aria-hidden="true">
              <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content border-0 shadow-lg">
                  <div class="modal-header bg-danger text-white border-0">
                    <h5 class="modal-title"><i class="bi bi-exclamation-triangle-fill me-2"></i>Beta Version Capacity</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                  </div>
                  <div class="modal-body p-4 text-center">
                    <i class="bi bi-cpu-fill text-danger mb-3" style="font-size: 3rem;"></i>
                    <h4>System Busy</h4>
                    <p class="text-muted mb-0">Our AI is currently processing heavy traffic. Please try a smaller file or wait 30 seconds before trying again.</p>
                  </div>
                  <div class="modal-footer border-0 justify-content-center">
                    <button type="button" class="btn btn-secondary px-4 rounded-pill" data-bs-dismiss="modal">Close</button>
                  </div>
                </div>
              </div>
            </div>`;
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            modalEl = document.getElementById('betaCapacityModal');
        }
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
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
