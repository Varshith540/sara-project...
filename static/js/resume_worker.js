/**
 * resume_worker.js — ResumeXpert Client-Side Processing Web Worker
 * =================================================================
 * Runs off the main thread to avoid freezing the UI.
 *
 * Supported operations (sent via postMessage from upload_controller.js):
 *
 *   { op: 'process_pdf',   file: <File>,   pdfJsWorkerSrc: <string> }
 *   { op: 'process_image', file: <File> }
 *
 * Progress events posted back to the main thread:
 *
 *   { type: 'progress', step: <string>, msg: <string> }
 *   { type: 'result',   payload: { mode, extractedText?, compressedBlob?, fileName, originalSize, finalSize } }
 *   { type: 'error',    msg: <string> }
 */

'use strict';

// ── PDF.js import (CDN, loaded lazily on first PDF operation) ─────────────────
// Uses the cdnjs UMD build (v3.x) which exposes pdfjsLib as a global —
// the .mjs ESM build from unpkg CANNOT be used with importScripts() in classic Workers.
let _pdfJs = null;
let _pdfJsWorkerSrc = null;

async function _ensurePdfJs(workerSrc) {
  if (_pdfJs) return _pdfJs;
  _pdfJsWorkerSrc = workerSrc;
  // importScripts is synchronous in classic Workers; must use a UMD/CJS build, not an .mjs module
  importScripts('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js');
  // After import, pdfjsLib is exposed as a global
  /* global pdfjsLib */
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;
  _pdfJs = pdfjsLib;
  return _pdfJs;
}

// ── Main message handler ──────────────────────────────────────────────────────
self.onmessage = async function (e) {
  const { op, file, pdfJsWorkerSrc } = e.data;

  try {
    if (op === 'process_pdf') {
      await handlePdf(file, pdfJsWorkerSrc);
    } else if (op === 'process_image') {
      await handleImage(file);
    } else {
      post({ type: 'error', msg: `Unknown op: ${op}` });
    }
  } catch (err) {
    post({ type: 'error', msg: `Worker error: ${err.message || err}` });
  }
};

// ── PDF handler ───────────────────────────────────────────────────────────────
async function handlePdf(file, workerSrc) {
  post({ type: 'progress', step: 'worker_start', msg: 'Reading PDF in browser...' });

  const pdfjsLib = await _ensurePdfJs(workerSrc);
  const arrayBuffer = await file.arrayBuffer();

  let doc;
  try {
    doc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  } catch (err) {
    // Encrypted / corrupt PDF — signal server-side fallback
    post({ type: 'result', payload: { mode: 'fallback', reason: 'pdf_unreadable', fileName: file.name, originalSize: file.size, finalSize: file.size } });
    return;
  }

  const numPages = doc.numPages;
  post({ type: 'progress', step: 'worker_reading', msg: `Extracting text from ${numPages} page(s)...` });

  let fullText = '';
  for (let i = 1; i <= numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items.map(item => item.str).join(' ');
    fullText += pageText + '\n';

    // Report page progress for long documents
    if (numPages > 5) {
      post({ type: 'progress', step: 'worker_reading', msg: `Reading page ${i}/${numPages}...` });
    }
  }

  // If extraction yielded nothing, the PDF is image-based — server Vision AI handles it
  if (fullText.trim().length < 50) {
    post({
      type: 'result',
      payload: {
        mode: 'image_pdf',         // server should treat it as an image
        fileName: file.name,
        originalSize: file.size,
        finalSize: file.size,
      }
    });
    return;
  }

  post({
    type: 'result',
    payload: {
      mode: 'text',
      extractedText: fullText.trim(),
      fileName: file.name,
      originalSize: file.size,
      finalSize: fullText.length,   // bytes sent → just text characters
    }
  });
}

// ── Image handler ─────────────────────────────────────────────────────────────
async function handleImage(file) {
  post({ type: 'progress', step: 'worker_compress', msg: 'Compressing image in browser...' });

  const originalSize = file.size;
  const MAX_SIDE = 1500;
  const QUALITY  = 0.65;

  // Read file into an ImageBitmap (available in Workers — no DOM needed)
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch (err) {
    // Browser can't decode this image type — fall back to server
    post({ type: 'result', payload: { mode: 'fallback', reason: 'image_undecodable', fileName: file.name, originalSize, finalSize: originalSize } });
    return;
  }

  // Compute scaled dimensions
  let { width, height } = bitmap;
  if (width > MAX_SIDE || height > MAX_SIDE) {
    const ratio = Math.min(MAX_SIDE / width, MAX_SIDE / height);
    width  = Math.round(width  * ratio);
    height = Math.round(height * ratio);
  }

  // Draw onto OffscreenCanvas
  const canvas = new OffscreenCanvas(width, height);
  const ctx    = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  // Encode as JPEG blob
  const compressedBlob = await canvas.convertToBlob({ type: 'image/jpeg', quality: QUALITY });
  const finalSize      = compressedBlob.size;

  post({
    type: 'result',
    payload: {
      mode:           'compressed_image',
      compressedBlob,
      fileName:       file.name.replace(/\.[^.]+$/, '_compressed.jpg'),
      originalSize,
      finalSize,
    }
  });
}

// ── Helper ────────────────────────────────────────────────────────────────────
function post(msg) {
  // Transfer blobs by reference (zero-copy) when possible
  if (msg.payload && msg.payload.compressedBlob) {
    self.postMessage(msg, [msg.payload.compressedBlob]);
  } else {
    self.postMessage(msg);
  }
}
