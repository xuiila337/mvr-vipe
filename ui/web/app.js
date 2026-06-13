/* ====================================
   MVR / PSP Check — Frontend Logic
   ==================================== */

let pdfLoaded = false;
let pageIndex = 0;
let pageCount = 0;
let zoom = 1.0;
let highlightsEnabled = true;
let docTypeStr = "None";
let highlightsList = [];
let zoomDebounceTimeout = null;

// Elements
let btnChoosePdf, zoomSlider, zoomValue, toggleHighlights, toggleDebug, toggleTheme, btnCheckUpdate;
let txtActual, txtExpected, txtDebug, mainContent, dropOverlay;
let btnPrev, btnNext, pageInfo, docType, pdfCanvas, pdfPlaceholder;
let btnSaveTxt, btnCopy, btnSaveBundle;

window.addEventListener('pywebviewready', function() {
    init();
});

function init() {
    // Select elements
    btnChoosePdf = document.getElementById('btn-choose-pdf');
    zoomSlider = document.getElementById('zoom-slider');
    zoomValue = document.getElementById('zoom-value');
    toggleHighlights = document.getElementById('toggle-highlights');
    toggleDebug = document.getElementById('toggle-debug');
    toggleTheme = document.getElementById('toggle-theme');
    btnCheckUpdate = document.getElementById('btn-check-update');
    
    txtActual = document.getElementById('txt-actual');
    txtExpected = document.getElementById('txt-expected');
    txtDebug = document.getElementById('txt-debug');
    mainContent = document.getElementById('main-content');
    dropOverlay = document.getElementById('drop-overlay');
    
    btnPrev = document.getElementById('btn-prev');
    btnNext = document.getElementById('btn-next');
    pageInfo = document.getElementById('page-info');
    docType = document.getElementById('doc-type');
    pdfCanvas = document.getElementById('pdf-canvas');
    pdfPlaceholder = document.getElementById('pdf-placeholder');
    
    btnSaveTxt = document.getElementById('btn-save-txt');
    btnCopy = document.getElementById('btn-copy');
    btnSaveBundle = document.getElementById('btn-save-bundle');
    
    // Bind Event Listeners
    btnChoosePdf.addEventListener('click', onChoosePdf);
    btnPrev.addEventListener('click', onPrevPage);
    btnNext.addEventListener('click', onNextPage);
    btnSaveTxt.addEventListener('click', onSaveTxt);
    btnCopy.addEventListener('click', onCopyClipboard);
    btnSaveBundle.addEventListener('click', onSaveBundle);
    btnCheckUpdate.addEventListener('click', onCheckUpdate);
    
    toggleHighlights.addEventListener('change', onToggleHighlights);
    toggleDebug.addEventListener('change', onToggleDebug);
    toggleTheme.addEventListener('change', onToggleTheme);
    
    zoomSlider.addEventListener('input', onZoomSliderInput);
    
    // Setup Drag & Drop
    setupDragAndDrop();
    
    // Initialize zoom slider background fill
    updateZoomSliderBackground(parseFloat(zoomSlider.value));
}

// === Event Handlers ===

async function onChoosePdf() {
    try {
        const res = await window.pywebview.api.choose_pdf();
        if (res && res.ok) {
            processPdfResult(res);
        }
    } catch (err) {
        alert("Error selecting PDF: " + err);
    }
}

function onPrevPage() {
    if (!pdfLoaded || pageIndex <= 0) return;
    pageIndex--;
    renderPage();
}

function onNextPage() {
    if (!pdfLoaded || pageIndex >= pageCount - 1) return;
    pageIndex++;
    renderPage();
}

async function onSaveTxt() {
    const text = txtActual.value.trim();
    if (!text) {
        alert("Nothing to save.");
        return;
    }
    const res = await window.pywebview.api.save_txt(text);
    if (res && res.ok) {
        alert("Saved successfully to:\n" + res.path);
    }
}

async function onCopyClipboard() {
    const text = txtActual.value.trim();
    if (!text) {
        alert("Nothing to copy.");
        return;
    }
    const res = await window.pywebview.api.copy_clipboard(text);
    if (res && res.ok) {
        // Simple visual feedback on copy button
        const oldText = btnCopy.textContent;
        btnCopy.textContent = "Copied!";
        setTimeout(() => {
            btnCopy.textContent = oldText;
        }, 1500);
    }
}

async function onSaveBundle() {
    if (!pdfLoaded) {
        alert("Load a PDF first.");
        return;
    }
    const expected = txtExpected.value.trim();
    try {
        const res = await window.pywebview.api.save_bundle(expected);
        if (res && res.ok) {
            alert("Debug bundle saved to:\n" + res.path);
        }
    } catch (err) {
        alert("Error saving bundle: " + err);
    }
}

async function onCheckUpdate() {
    const originalText = btnCheckUpdate.innerHTML;
    btnCheckUpdate.innerHTML = `<span class="spinner"></span>Checking...`;
    btnCheckUpdate.disabled = true;
    
    try {
        const res = await window.pywebview.api.check_updates();
        if (res && res.ok) {
            if (res.has_update) {
                if (confirm(`New version available: ${res.version}\n\nNotes:\n${res.notes}\n\nWould you like to download and install it now?`)) {
                    btnCheckUpdate.innerHTML = `<span class="spinner"></span>Updating...`;
                    const installRes = await window.pywebview.api.download_and_install_update(res.download_url, res.version);
                    if (installRes && !installRes.ok) {
                        alert("Update failed:\n" + installRes.error);
                    }
                }
            } else {
                alert(res.message || "You have the latest version.");
            }
        } else {
            alert(res ? res.message : "Failed to check updates.");
        }
    } catch (err) {
        alert("Error checking updates: " + err);
    } finally {
        btnCheckUpdate.innerHTML = originalText;
        btnCheckUpdate.disabled = false;
    }
}

function onToggleHighlights(e) {
    highlightsEnabled = e.target.checked;
    if (pdfLoaded) {
        renderPage();
    }
}

function onToggleDebug(e) {
    if (e.target.checked) {
        mainContent.classList.add('with-debug');
        document.querySelector('.debug-panel').classList.add('visible');
    } else {
        mainContent.classList.remove('with-debug');
        document.querySelector('.debug-panel').classList.remove('visible');
    }
    if (pdfLoaded) {
        renderPage();
    }
}

function onToggleTheme(e) {
    if (e.target.checked) {
        document.body.classList.remove('light-theme');
    } else {
        document.body.classList.add('light-theme');
    }
}

function onZoomSliderInput(e) {
    const val = parseFloat(e.target.value);
    zoom = val;
    zoomValue.textContent = val.toFixed(2) + "x";
    updateZoomSliderBackground(val);
    
    // Debounce rendering to avoid UI stutter during slider movement
    if (zoomDebounceTimeout) clearTimeout(zoomDebounceTimeout);
    zoomDebounceTimeout = setTimeout(() => {
        if (pdfLoaded) {
            renderPage();
        }
    }, 150);
}

function updateZoomSliderBackground(val) {
    const min = parseFloat(zoomSlider.min);
    const max = parseFloat(zoomSlider.max);
    const pct = ((val - min) / (max - min)) * 100;
    zoomSlider.style.background = `linear-gradient(to right, var(--accent) 0%, var(--accent) ${pct}%, var(--card-border-muted) ${pct}%, var(--card-border-muted) 100%)`;
}

// === PDF Parsing and Rendering ===

function processPdfResult(res) {
    pdfLoaded = true;
    pageIndex = 0;
    pageCount = res.page_count;
    docTypeStr = res.doc_type;
    
    txtActual.value = res.actual_text;
    
    try {
        txtDebug.value = res.debug_log;
    } catch (e) {
        txtDebug.value = "Failed to parse debug log: " + e;
    }
    
    docType.textContent = "Doc: " + docTypeStr;
    
    // Check for issues/errors
    if (res.issues && res.issues.length > 0) {
        const errors = res.issues.filter(i => i.level === "error").map(i => i.message);
        if (errors.length > 0) {
            alert("Parsing issues encountered:\n\n" + errors.join("\n"));
        }
    }
    
    renderPage();
}

async function renderPage() {
    if (!pdfLoaded) return;
    
    pageInfo.textContent = `Page: ${pageIndex + 1}/${pageCount}`;
    
    pdfPlaceholder.style.display = 'none';
    pdfCanvas.style.display = 'block';
    
    try {
        const res = await window.pywebview.api.render_page(pageIndex, zoom);
        if (!res || !res.ok) {
            pdfPlaceholder.textContent = "Error rendering PDF page";
            pdfPlaceholder.style.display = 'flex';
            pdfCanvas.style.display = 'none';
            return;
        }
        
        const img = new Image();
        img.onload = async function() {
            const ctx = pdfCanvas.getContext('2d');
            pdfCanvas.width = res.width;
            pdfCanvas.height = res.height;
            ctx.drawImage(img, 0, 0);
            
            if (highlightsEnabled) {
                await drawHighlights(ctx);
            }
        };
        img.src = 'data:image/png;base64,' + res.base64_png;
    } catch (err) {
        console.error("Render error: ", err);
    }
}

async function drawHighlights(ctx) {
    try {
        const res = await window.pywebview.api.get_highlights(pageIndex, zoom);
        if (res && res.rects) {
            highlightsList = res.rects;
            ctx.strokeStyle = "rgba(255, 0, 0, 0.85)";
            ctx.lineWidth = 2;
            ctx.fillStyle = "rgba(255, 0, 0, 0.15)";
            
            for (const r of highlightsList) {
                const width = r.x1 - r.x0;
                const height = r.bottom - r.top;
                ctx.fillRect(r.x0, r.top, width, height);
                ctx.strokeRect(r.x0, r.top, width, height);
            }
        }
    } catch (err) {
        console.error("Error drawing highlights: ", err);
    }
}

// === Drag and Drop ===

function setupDragAndDrop() {
    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    // Show overlay when dragging file over window
    let dragCounter = 0;
    
    document.addEventListener('dragenter', () => {
        dragCounter++;
        dropOverlay.classList.add('active');
    }, false);
    
    document.addEventListener('dragleave', () => {
        dragCounter--;
        if (dragCounter === 0) {
            dropOverlay.classList.remove('active');
        }
    }, false);
    
    document.addEventListener('drop', async (e) => {
        dragCounter = 0;
        dropOverlay.classList.remove('active');
        
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            const file = files[0];
            
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                alert("Please drop a PDF file.");
                return;
            }
            
            const reader = new FileReader();
            reader.onload = async function(evt) {
                try {
                    const arrayBuffer = evt.target.result;
                    const base64 = arrayBufferToBase64(arrayBuffer);
                    
                    const res = await window.pywebview.api.process_dropped_pdf_bytes(base64, file.name);
                    if (res && res.ok) {
                        processPdfResult(res);
                    } else if (res && res.error) {
                        alert("Error loading dropped PDF: " + res.error);
                    }
                } catch (err) {
                    alert("Error processing dropped file: " + err);
                }
            };
            reader.onerror = function() {
                alert("Failed to read the dropped file.");
            };
            reader.readAsArrayBuffer(file);
        }
    }, false);
}

function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

// Polyfill for endsWith if needed
if (!String.prototype.endsWith) {
    String.prototype.endsWith = function(suffix) {
        return this.indexOf(suffix, this.length - suffix.length) !== -1;
    };
}
