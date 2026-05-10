// static/js/worker.js
// Dedicated Web Worker for Edge Computing (PDF Rasterization)

// Import the pdf.js core library and worker
importScripts('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js');

// Set worker source internally
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

self.onmessage = async function(e) {
    try {
        console.log("[Web Worker] Received PDF buffer. Starting background rasterization...");
        const arrayBuffer = e.data.arrayBuffer;
        
        // Load PDF document
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;
        
        const maxPages = Math.min(2, pdf.numPages);
        const processedImages = [];
        
        for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
            const page = await pdf.getPage(pageNum);
            const viewport = page.getViewport({ scale: 1.0 }); // ~72 DPI
            
            // Use OffscreenCanvas to render completely off the main UI thread
            const canvas = new OffscreenCanvas(viewport.width, viewport.height);
            const ctx = canvas.getContext('2d');
            
            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };
            
            await page.render(renderContext).promise;
            
            // Convert OffscreenCanvas to a blob
            const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.6 });
            
            // Convert Blob to Base64 (Worker safe, avoids FileReader which can be inconsistent)
            const buffer = await blob.arrayBuffer();
            let binary = '';
            const bytes = new Uint8Array(buffer);
            const len = bytes.byteLength;
            for (let i = 0; i < len; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            const base64 = btoa(binary);
            const dataUrl = `data:image/jpeg;base64,${base64}`;
            
            processedImages.push(dataUrl);
        }
        
        console.log(`[Web Worker] Success: Rasterized ${processedImages.length} pages invisibly.`);
        self.postMessage({ status: 'success', data: processedImages });
        
    } catch (error) {
        console.error("[Web Worker] Fatal processing error:", error);
        self.postMessage({ status: 'error', error: error.toString() });
    }
};
