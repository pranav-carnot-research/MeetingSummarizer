document.addEventListener('DOMContentLoaded', () => {
    // Global variables to store state
    let currentJobId = null;
    let currentTranscript = null;
    let currentResult = null;
    let pollInterval = null;

    // Add global context section function
    window.addMeetingContextSection = function() {
        console.log("ADDING MEETING CONTEXT SECTION - Starting...");
        
        // Remove any existing context section to avoid duplicates
        const existingSection = document.getElementById('meetingContextSection');
        if (existingSection) {
            existingSection.remove();
            console.log("Removed existing context section");
        }
        
        // Create a very visible context input section
        const contextSection = document.createElement('div');
        contextSection.id = 'meetingContextSection';
        contextSection.className = 'card mt-3 mb-3';
        contextSection.style.border = '2px solid #007bff';  // Blue border to make it stand out
        contextSection.style.boxShadow = '0 0 10px rgba(0,123,255,0.5)';  // Add glow effect
        
        contextSection.innerHTML = `
            <div class="card-header bg-primary text-white">
                <h4>Additional Meeting Context (Optional)</h4>
                <p class="mb-0">Provide context to improve summary quality</p>
            </div>
            <div class="card-body">
                <textarea id="meetingContext" class="form-control" rows="4" 
                    placeholder="Example: This is a weekly team meeting for the marketing department. The main goals were to review Q2 campaign results and plan for Q3."></textarea>
                <div class="form-text text-muted mt-2">
                    Adding context helps our AI create a more accurate and relevant summary.
                </div>
            </div>
        `;
        
        console.log("Context section created, now adding to page...");
        
        // Try multiple insertion methods to ensure it appears
        
        // Method 1: Insert before summarize button
        const summarizeBtn = document.getElementById('summarizeAudioBtn');
        if (summarizeBtn && summarizeBtn.parentNode) {
            summarizeBtn.parentNode.insertBefore(contextSection, summarizeBtn);
            console.log("SUCCESS: Added context before summarize button");
            return true;
        }
        
        // Method 2: Insert after transcript preview
        const transcriptPreview = document.getElementById('transcriptPreview');
        if (transcriptPreview) {
            transcriptPreview.after(contextSection);
            console.log("SUCCESS: Added context after transcript preview");
            return true;
        }
        
        // Method 3: Insert at end of audio form
        const audioForm = document.getElementById('audioForm');
        if (audioForm) {
            audioForm.appendChild(contextSection);
            console.log("SUCCESS: Added context at end of audio form");
            return true;
        }
        
        // Method 4: Last resort - add to main container
        const container = document.querySelector('.container');
        if (container) {
            container.appendChild(contextSection);
            console.log("SUCCESS: Added context to main container");
            return true;
        }
        
        console.error("FAILED: Could not find any suitable location to add context section");
        return false;
    };

    // Form submission handlers
    document.getElementById('audioForm').addEventListener('submit', handleAudioFormSubmit);
    document.getElementById('pasteTextForm').addEventListener('submit', handlePasteTextFormSubmit);
    document.getElementById('uploadTextForm').addEventListener('submit', handleUploadTextFormSubmit);
    
    // Button event listeners
    document.getElementById('summarizeAudioBtn').addEventListener('click', handleSummarizeAudioClick);
    document.getElementById('summarizeTextBtn').addEventListener('click', handleSummarizeTextClick);
    document.getElementById('downloadJsonBtn').addEventListener('click', handleDownloadJson);
    document.getElementById('downloadTextBtn').addEventListener('click', handleDownloadText);
    
    const refineBtn = document.getElementById('refineTranscriptBtn');
    if (refineBtn) {
        refineBtn.addEventListener('click', handleRefineTranscriptClick);
    }

    /**
     * Handle audio form submission
     */
    async function handleAudioFormSubmit(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const audioFile = formData.get('file');
        
        if (!audioFile || audioFile.size === 0) {
            showAlert('Please select an audio file to upload', 'danger');
            return;
        }
        
        try {
            // Instantly bind local audio URL to the meeting audio player for click-to-seek sync
            const localAudioUrl = URL.createObjectURL(audioFile);
            window.currentAudioStreamUrl = localAudioUrl;
            const meetingPlayer = document.getElementById('meetingAudioPlayer');
            if (meetingPlayer) {
                meetingPlayer.src = localAudioUrl;
                meetingPlayer.classList.remove('d-none');
            }

            // Show processing status
            document.getElementById('audioProcessingStatus').classList.remove('d-none');
            updateAudioProgress(0, 'Starting audio processing...');
            
            // Submit the form
            const response = await fetch('/api/upload-audio', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            // Start polling for status updates
            startAudioJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error uploading audio:', error);
            updateAudioProgress(0, `Error: ${error.message}`, true);
        }
    }
    
    /**
     * Poll for audio processing job status
     */
    function startAudioJobPolling(jobId) {
        clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                console.log(`Polling job status for job ID: ${jobId}`);
                const response = await fetch(`/api/job/${jobId}`);
                
                if (!response.ok) {
                    throw new Error(`Server responded with ${response.status}`);
                }
                
                const data = await response.json();
                console.log("Received job status data:", data);
                
                // Add debug logging for confidence metrics
                if (data.result) {
                    console.log("Result data received:", data.result);
                    if (data.result.confidence_metrics) {
                        console.log("Confidence metrics found:", data.result.confidence_metrics);
                    } else {
                        console.log("No confidence metrics in result data");
                    }
                }
                
                // Update progress
                updateAudioProgress(data.progress || 0, data.message || 'Processing...');
                
                // Check if job is complete
                if (data.status === 'completed') {
                    console.log("Job completed successfully");
                    clearInterval(pollInterval);
                    
                    // Store transcript data
                    if (data.result && data.result.transcript) {
                        console.log("Transcript data received");
                        currentTranscript = data.result;
                        
                        // Show detected language in UI
                        if (data.result.language) {
                            console.log("Detected language:", data.result.language);
                            const detectedLang = data.result.language;
                            const languageDisplay = getLanguageDisplayName(detectedLang);
                            
                            // Update message with clear language detection info
                            let message = `Processing complete. `;
                            
                            // If language was auto-detected, make it clearer
                            const selectedLanguage = document.getElementById('audioLanguage').value;
                            if (selectedLanguage === 'auto') {
                                message += `Language automatically detected as: ${languageDisplay} (${detectedLang})`;
                            } else {
                                message += `Using selected language: ${languageDisplay}`;
                            }
                            
                            // Add confidence information if available
                            if (data.result.confidence_metrics && data.result.confidence_metrics.average) {
                                const avgConfidence = data.result.confidence_metrics.average;
                                message += `<br>Average transcription confidence: <strong>${avgConfidence}%</strong>`;
                                
                                // Add warning for low confidence
                                if (data.result.confidence_metrics.low_confidence_percentage > 20) {
                                    message += `<br><span class="text-warning">⚠️ ${data.result.confidence_metrics.low_confidence_percentage}% of segments have low confidence</span>`;
                                }
                            }
                            
                            updateAudioProgress(100, message);
                            
                            // Add confidence stats to the UI only once
                            if (data.result.confidence_metrics) {
                                console.log("Creating confidence notice box with metrics:", data.result.confidence_metrics);
                                
                                // Remove existing notice if present
                                const existingNotice = document.getElementById('confidenceNotice');
                                if (existingNotice) {
                                    console.log("Removing existing confidence notice");
                                    existingNotice.remove();
                                }
                                
                                const notice = document.createElement('div');
                                notice.id = 'confidenceNotice';
                                notice.className = 'alert alert-info mt-2';
                                
                                // Log the metrics being used
                                const metrics = data.result.confidence_metrics;
                                console.log("Using confidence metrics:", {
                                    average: metrics.average,
                                    min: metrics.min,
                                    max: metrics.max
                                });
                                
                                notice.innerHTML = `
                                    <h5>Transcription Confidence</h5>
                                    <div class="row">
                                        <div class="col-md-6">
                                            <p><strong>Average:</strong> ${metrics.average}%</p>
                                            <p><strong>Range:</strong> ${metrics.min}% - ${metrics.max}%</p>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="progress mb-2" style="height: 20px;">
                                                <div class="progress-bar bg-success" role="progressbar" 
                                                    style="width: ${metrics.average}%" 
                                                    aria-valuenow="${metrics.average}" 
                                                    aria-valuemin="0" aria-valuemax="100">
                                                    ${metrics.average}%
                                                </div>
                                            </div>
                                            <small class="text-muted">
                                                <span class="badge bg-success me-1">✓</span> High confidence (90%+)<br>
                                                <span class="badge bg-warning text-dark me-1">~</span> Medium confidence (70-89%)<br>
                                                <span class="badge bg-danger me-1">?</span> Low confidence (<70%)
                                            </small>
                                        </div>
                                    </div>
                                `;
                                
                                const transcriptPreview = document.getElementById('transcriptPreview');
                                if (transcriptPreview) {
                                    console.log("Appending confidence notice to transcript preview");
                                    transcriptPreview.appendChild(notice);
                                } else {
                                    console.error("Could not find transcriptPreview element");
                                }
                            } else {
                                console.log("No confidence metrics available in result data");
                            }
                        }
                        
                        // Setup audio player if permanent recording exists
                        const audioPlayer = document.getElementById('meetingAudioPlayer');
                        if (audioPlayer && currentJobId) {
                            audioPlayer.src = `/recordings/${currentJobId}.wav`;
                            audioPlayer.classList.remove('d-none');
                        }

                        // Render word-level interactive color-coded transcript
                        const segmentsList = data.result.segments || data.result.transcript || data.result.raw_transcription;
                        if (segmentsList && segmentsList.length > 0) {
                            renderInteractiveTranscript(segmentsList, 'transcriptPreviewText');
                        } else {
                            // Fallback to formatted transcript lines
                            const previewText = document.getElementById('transcriptPreviewText');
                            const formattedTranscript = data.result.formatted_transcript || [];
                            previewText.innerHTML = formattedTranscript.map(line => `<div>${line}</div>`).join('');
                        }
                        
                        document.getElementById('transcriptPreview').classList.remove('d-none');
                        
                        // Add context section after showing transcript
                        console.log("Transcript preview displayed, adding context section...");
                        setTimeout(window.addMeetingContextSection, 100);
                    }
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    updateAudioProgress(0, `Error: ${data.message}`, true);
                }
                
            } catch (error) {
                console.error('Error polling job status:', error);
                clearInterval(pollInterval);
                updateAudioProgress(0, `Error checking job status: ${error.message}`, true);
            }
        }, 1000);
    }
    
    function addConfidenceIndicators(text, confidence) {
        if (!confidence) return text;
        
        let indicator = "";
        let badgeClass = "";
        
        if (confidence >= 90) {
            indicator = "✓";
            badgeClass = "bg-success";
        } else if (confidence >= 70) {
            indicator = "~";
            badgeClass = "bg-warning text-dark";
        } else {
            indicator = "?";
            badgeClass = "bg-danger";
        }
        
        return `<span class="badge ${badgeClass} me-1" title="${confidence}% confidence">${indicator}</span> ${text}`;
    }

    /**
     * Render word-level interactive color-coded transcript
     */
    function renderInteractiveTranscript(segments, targetElementId) {
        const target = document.getElementById(targetElementId);
        if (!target) return;
        
        // Collect all distinct original speaker names
        const distinctSpeakers = new Set();
        segments.forEach((seg, sIdx) => {
            let rawSpeaker = seg.speaker !== undefined && seg.speaker !== null ? String(seg.speaker) : (seg.speaker_id !== undefined ? String(seg.speaker_id) : `Speaker ${sIdx + 1}`);
            let speaker = rawSpeaker;
            if (rawSpeaker === 'SPEAKER_00' || rawSpeaker === '0') speaker = 'Speaker 1';
            else if (rawSpeaker === 'SPEAKER_01' || rawSpeaker === '1') speaker = 'Speaker 2';
            else if (rawSpeaker === 'SPEAKER_02' || rawSpeaker === '2') speaker = 'Speaker 3';
            else if (rawSpeaker.startsWith('SPEAKER_')) {
                const num = parseInt(rawSpeaker.replace('SPEAKER_', ''), 10);
                speaker = !isNaN(num) ? `Speaker ${num + 1}` : rawSpeaker;
            }
            distinctSpeakers.add(speaker);
        });

        let html = '';

        // Render Speaker Rename Quick Toolbar
        if (distinctSpeakers.size > 0) {
            html += `<div class="card mb-3 border-info shadow-sm">`;
            html += `<div class="card-body py-2 px-3 bg-light">`;
            html += `<div class="d-flex align-items-center justify-content-between flex-wrap gap-2">`;
            html += `<span class="fw-bold text-dark small">👤 Edit Speaker Names for Summary:</span>`;
            html += `<div class="d-flex flex-wrap gap-3 align-items-center">`;
            distinctSpeakers.forEach(spk => {
                html += `<div class="d-flex align-items-center gap-1">`;
                html += `<span class="badge bg-primary me-1">${spk} ➔</span>`;
                html += `<input type="text" class="form-control form-control-sm speaker-rename-input" data-original-speaker="${spk}" value="${spk}" placeholder="Enter name e.g. Pranav" style="width: 160px; font-weight: bold;">`;
                html += `</div>`;
            });
            html += `</div></div></div></div>`;
        }
        
        segments.forEach((seg, sIdx) => {
            let rawSpeaker = seg.speaker !== undefined && seg.speaker !== null ? String(seg.speaker) : (seg.speaker_id !== undefined ? String(seg.speaker_id) : `Speaker ${sIdx + 1}`);
            let speaker = rawSpeaker;
            if (rawSpeaker === 'SPEAKER_00' || rawSpeaker === '0') speaker = 'Speaker 1';
            else if (rawSpeaker === 'SPEAKER_01' || rawSpeaker === '1') speaker = 'Speaker 2';
            else if (rawSpeaker === 'SPEAKER_02' || rawSpeaker === '2') speaker = 'Speaker 3';
            else if (rawSpeaker.startsWith('SPEAKER_')) {
                const num = parseInt(rawSpeaker.replace('SPEAKER_', ''), 10);
                speaker = !isNaN(num) ? `Speaker ${num + 1}` : rawSpeaker;
            }
            
            const segStart = seg.start !== undefined ? seg.start : (seg.start_time !== undefined ? seg.start_time : 0);
            const segEnd = seg.end !== undefined ? seg.end : (seg.end_time !== undefined ? seg.end_time : segStart + 2);
            const startTime = typeof formatTime === 'function' ? formatTime(segStart) : `${Math.floor(segStart)}s`;
            const segConf = seg.confidence !== undefined && seg.confidence !== null ? Math.round(seg.confidence) : 85;
            
            let segBadge = 'bg-success';
            if (segConf < 65) segBadge = 'bg-danger';
            else if (segConf < 90) segBadge = 'bg-warning text-dark';
            
            html += `<div class="mb-3 p-2 rounded border-start border-3 ${segConf < 65 ? 'border-danger bg-light' : 'border-primary'}" data-segment-id="${sIdx}" data-start="${segStart}" data-end="${segEnd}">`;
            html += `<div class="d-flex justify-content-between text-muted small mb-1">`;
            html += `<span class="d-inline-flex align-items-center gap-1"><strong class="speaker-name text-primary text-decoration-underline" contenteditable="true" spellcheck="false" data-original-speaker="${speaker}" title="Click to edit speaker name (e.g. rename to Pranav)">${speaker}</strong> <span title="Click to edit speaker name">✏️</span> ${startTime ? `<span class="segment-time ms-1">(${startTime})</span>` : ''}</span>`;
            html += `<span class="badge ${segBadge}">Confidence: ${segConf}%</span>`;
            html += `</div><div>`;
            
            const wordsList = (seg.words && seg.words.length > 0) ? seg.words : (seg.text ? seg.text.split(' ').map(wText => ({ word: wText, confidence: segConf, start: segStart, end: segEnd })) : []);
            
            if (wordsList.length > 0) {
                wordsList.forEach(w => {
                    const wordText = w.word || '';
                    const conf = w.confidence !== undefined && w.confidence !== null ? Math.round(w.confidence) : segConf;
                    const status = w.status || (conf < 65 ? 'NEEDS_REVIEW' : (conf < 90 ? 'MEDIUM_CONFIDENCE' : 'HIGH_CONFIDENCE'));
                    
                    let wordClass = 'word-high';
                    let tooltipText = `Confidence: ${conf}%`;
                    
                    if (status === 'AI_CORRECTED' || w.original_word) {
                        wordClass = 'word-ai-corrected';
                        tooltipText = `✨ Auto-Corrected (Original: "${w.original_word || 'misheard'}" ➔ "${wordText}")`;
                    } else if (status === 'USER_VERIFIED') {
                        wordClass = 'word-user-verified';
                        tooltipText = `✓ User Verified`;
                    } else if (conf < 65 || status === 'NEEDS_REVIEW') {
                        wordClass = 'word-low';
                        tooltipText = `⚠️ Low Confidence (${conf}%). Click to listen / edit.`;
                    } else if (conf < 90) {
                        wordClass = 'word-medium';
                        tooltipText = `Medium Confidence (${conf}%)`;
                    }
                    
                    const wStart = w.start !== undefined ? w.start : segStart;
                    const wEnd = w.end !== undefined ? w.end : segEnd;
                    
                    html += `<span class="word-span ${wordClass}" data-start="${wStart}" data-end="${wEnd}" data-confidence="${conf}" data-status="${status}" contenteditable="true" spellcheck="false">`;
                    html += `${wordText}`;
                    html += `<span class="word-tooltip">${tooltipText}</span>`;
                    html += `</span> `;
                });
            } else {
                html += `<span>${seg.text}</span>`;
            }
            
            html += `</div></div>`;
        });
        
        target.innerHTML = html;
        attachWordSyncListeners(targetElementId);
        attachSpeakerRenameListeners(targetElementId);
    }

    /**
     * Attach click-to-play audio sync & inline edit listeners
     */
    function attachWordSyncListeners(targetElementId) {
        const container = document.getElementById(targetElementId);
        if (!container) return;
        
        // Use event delegation for reliable click handling
        container.removeEventListener('click', container._wordSyncClickHandler);
        container._wordSyncClickHandler = function(e) {
            const wordEl = e.target.closest('.word-span');
            if (!wordEl) return;
            
            let audioPlayer = null;
            if (targetElementId === 'recordTranscriptPreviewText') {
                audioPlayer = document.getElementById('recordedAudioPlayback') || document.getElementById('meetingAudioPlayer');
            } else {
                audioPlayer = document.getElementById('meetingAudioPlayer') || document.getElementById('recordedAudioPlayback');
            }
            
            if (!audioPlayer) return;
            
            // Ensure audio player has a valid audio source URL
            if ((!audioPlayer.src || audioPlayer.src.endsWith('/')) && window.currentAudioStreamUrl) {
                audioPlayer.src = window.currentAudioStreamUrl;
            }
            
            audioPlayer.classList.remove('d-none');
            
            const start = parseFloat(wordEl.getAttribute('data-start'));
            
            // Find parent speaker segment and its end timestamp
            const segmentEl = wordEl.closest('[data-segment-id]');
            const segmentEnd = segmentEl ? parseFloat(segmentEl.getAttribute('data-end')) : parseFloat(wordEl.getAttribute('data-end'));
            
            // Clear any active stop target immediately
            audioPlayer.playbackStopTarget = null;
            
            // Setup dynamic stop target AFTER the seek completes to prevent race conditions
            if (!isNaN(segmentEnd)) {
                const onSeeked = function() {
                    audioPlayer.playbackStopTarget = segmentEnd;
                    console.log(`Seek complete: play until ${segmentEnd}s`);
                    audioPlayer.removeEventListener('seeked', onSeeked);
                };
                audioPlayer.addEventListener('seeked', onSeeked);
            }
            
            // Bind timeupdate event handler to enforce segment playback restriction (only once)
            if (!audioPlayer._playbackStopListenerAttached) {
                audioPlayer.addEventListener('timeupdate', function() {
                    // Ignore checks while seeking is active
                    if (this.seeking) return;
                    
                    if (this.playbackStopTarget !== undefined && this.playbackStopTarget !== null) {
                        if (this.currentTime >= this.playbackStopTarget) {
                            console.log(`Pausing audio playback automatically at segment end: ${this.playbackStopTarget}s`);
                            this.pause();
                            this.playbackStopTarget = null; // Clear stop target
                        }
                    }
                });
                audioPlayer._playbackStopListenerAttached = true;
            }
            
            if (!isNaN(start)) {
                try {
                    audioPlayer.currentTime = start;
                    const playPromise = audioPlayer.play();
                    if (playPromise !== undefined) {
                        playPromise.then(() => {
                            console.log(`Audio playback seeking to ${start}s`);
                        }).catch(err => console.log("Audio playback notice:", err));
                    }
                } catch (seekErr) {
                    console.warn("Audio seek notice:", seekErr);
                }
                
                container.querySelectorAll('.word-span').forEach(el => el.classList.remove('playing-word'));
                wordEl.classList.add('playing-word');
            }
        };
        container.addEventListener('click', container._wordSyncClickHandler);

        // Attach focus and blur event listeners for inline human editing
        container.querySelectorAll('.word-span').forEach(wordEl => {
            // Track the original word text on focus to compare later
            wordEl.addEventListener('focus', function() {
                const textNodes = Array.from(this.childNodes).filter(node => node.nodeType === Node.TEXT_NODE);
                this._originalText = textNodes.map(n => n.textContent).join('').trim();
            });

            wordEl.addEventListener('blur', function() {
                const textNodes = Array.from(this.childNodes).filter(node => node.nodeType === Node.TEXT_NODE);
                const newText = textNodes.map(n => n.textContent).join('').trim();
                
                // Only mark as user verified if the text actually changed
                if (this._originalText !== undefined && newText !== this._originalText) {
                    this.setAttribute('data-status', 'USER_VERIFIED');
                    this.className = 'word-span word-user-verified';
                    const tooltip = this.querySelector('.word-tooltip');
                    if (tooltip) tooltip.textContent = '✓ User Verified';

                    // Save new term to active learning glossary
                    if (newText && newText.length > 2) {
                        fetch('/api/vocabulary', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ term: newText })
                        }).then(res => res.json()).then(d => {
                            console.log("Saved term to active glossary:", d);
                        }).catch(e => console.log("Glossary save deferred:", e));
                    }
                }
            });
        });
    }

    /**
     * Attach real-time speaker rename synchronization listeners
     */
    function attachSpeakerRenameListeners(targetElementId) {
        const container = document.getElementById(targetElementId);
        if (!container) return;

        // 1. Listen for toolbar input changes
        const renameInputs = container.querySelectorAll('.speaker-rename-input');
        renameInputs.forEach(inputEl => {
            inputEl.addEventListener('input', function() {
                const origSpk = this.getAttribute('data-original-speaker');
                const newName = this.value.trim() || origSpk;
                
                // Update all matching speaker-name tags in this container
                container.querySelectorAll(`.speaker-name[data-original-speaker="${origSpk}"]`).forEach(spkEl => {
                    spkEl.innerText = newName;
                });
            });
        });

        // 2. Listen for direct inline <strong class="speaker-name"> edits
        const speakerEls = container.querySelectorAll('.speaker-name');
        speakerEls.forEach(spkEl => {
            spkEl.addEventListener('input', function() {
                const origSpk = this.getAttribute('data-original-speaker');
                const newName = this.innerText.trim();
                
                // Update matching toolbar input if present
                const toolbarInput = container.querySelector(`.speaker-rename-input[data-original-speaker="${origSpk}"]`);
                if (toolbarInput) {
                    toolbarInput.value = newName;
                }
                
                // Update all other matching speaker tags
                container.querySelectorAll(`.speaker-name[data-original-speaker="${origSpk}"]`).forEach(otherEl => {
                    if (otherEl !== spkEl) {
                        otherEl.innerText = newName;
                    }
                });
            });
        });
    }

    /**
     * Helper to extract unique participant names from edited transcript text
     */
    function extractParticipantsFromEditedText(transcriptText) {
        const speakers = new Set();
        if (!transcriptText) return [];
        const lines = transcriptText.split('\n');
        lines.forEach(line => {
            const parts = line.split(':', 1);
            if (parts.length > 0 && parts[0].trim()) {
                let spk = parts[0].trim().replace(/^\[.*?\]\s*/, '');
                if (spk) speakers.add(spk);
            }
        });
        return Array.from(speakers);
    }

    /**
     * Handle Refine Low-Confidence Words with Local AI (Ollama)
     */
    async function handleRefineTranscriptClick(event) {
        const btn = event ? event.currentTarget : (document.getElementById('refineTranscriptBtn') || document.getElementById('refineRecordTranscriptBtn'));
        if (!btn || !currentJobId) {
            alert('No active audio transcript available to refine.');
            return;
        }
        
        const targetTextId = (btn.id === 'refineRecordTranscriptBtn') ? 'recordTranscriptPreviewText' : 'transcriptPreviewText';
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Refining with Local AI (Ollama)...`;
        
        try {
            const response = await fetch('/api/refine-transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: currentJobId })
            });
            
            const data = await response.json();
            if (response.ok && data.status === 'success' && data.segments) {
                if (currentTranscript) {
                    currentTranscript.segments = data.segments;
                }
                renderInteractiveTranscript(data.segments, targetTextId);
                alert('✨ Transcript successfully refined using Local AI (Ollama)!');
            } else {
                alert('Error refining transcript: ' + (data.detail || 'Failed to refine with local AI. Make sure Ollama is running.'));
            }
        } catch (err) {
            console.error('Refine error:', err);
            alert('Failed to connect to Local LLM refinement service: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }

    /**
     * Update audio processing progress
     */
    function updateAudioProgress(progress, message, isError = false) {
        const progressBar = document.getElementById('audioProgressBar');
        const statusText = document.getElementById('audioStatusText');
        
        progressBar.style.width = `${progress}%`;
        statusText.innerHTML = message;
        
        if (isError) {
            progressBar.classList.remove('bg-primary');
            progressBar.classList.add('bg-danger');
        } else {
            progressBar.classList.remove('bg-danger');
            progressBar.classList.add('bg-primary');
        }

        // Add context input after transcript is shown
        if (progress === 100 && !isError) {
            setTimeout(addContextInput, 500); // Short delay to ensure DOM is updated
        }
    }
    
    /**
     * Add context input section to the UI
     */
    function addContextInput() {
        // Check if we already added the context input
        if (document.getElementById('meetingContextSection')) {
            return;
        }
        
        // Create the context input section
        const contextSection = document.createElement('div');
        contextSection.id = 'meetingContextSection';
        contextSection.className = 'card mt-3 mb-3';
        contextSection.innerHTML = `
            <div class="card-header">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="enableContextInput">
                    <label class="form-check-label" for="enableContextInput">
                        <strong>Add Meeting Context</strong> (Optional)
                    </label>
                </div>
            </div>
            <div class="card-body" id="contextInputBody" style="display: none;">
                <p class="text-muted">Provide additional context about this meeting to improve summary quality:</p>
                <textarea id="meetingContext" class="form-control" rows="3" 
                    placeholder="Example: This is a weekly team meeting for the marketing department. The main goals were to review Q2 campaign results and plan for Q3."></textarea>
            </div>
        `;
        
        // Insert before the summarize button
        const audioProcessingStatus = document.getElementById('audioProcessingStatus');
        audioProcessingStatus.parentNode.insertBefore(contextSection, 
            document.getElementById('summarizeAudioBtn').parentNode);
        
        // Add toggle functionality
        document.getElementById('enableContextInput').addEventListener('change', function() {
            document.getElementById('contextInputBody').style.display = 
                this.checked ? 'block' : 'none';
        });
    }
    
    /**
     * Extract updated transcript text from UI DOM including human edits
     */
    function extractEditedTranscriptFromDOM(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const segmentDivs = container.querySelectorAll('[data-segment-id]');
        if (!segmentDivs || segmentDivs.length === 0) {
            return container.innerText.trim();
        }

        const lines = [];
        segmentDivs.forEach(segEl => {
            const headerEl = segEl.querySelector('strong');
            const speakerName = headerEl ? headerEl.innerText.trim() : 'Speaker 1';
            
            const wordSpans = segEl.querySelectorAll('.word-span');
            let text = '';
            if (wordSpans && wordSpans.length > 0) {
                const wordTexts = [];
                wordSpans.forEach(wEl => {
                    let wText = '';
                    wEl.childNodes.forEach(node => {
                        if (node.nodeType === Node.TEXT_NODE) {
                            wText += node.textContent;
                        }
                    });
                    if (!wText) {
                        const tooltip = wEl.querySelector('.word-tooltip');
                        wText = wEl.innerText.replace(tooltip ? tooltip.innerText : '', '').trim();
                    }
                    if (wText) wordTexts.push(wText.trim());
                });
                text = wordTexts.join(' ');
            } else {
                text = segEl.innerText.trim();
            }

            if (text) {
                lines.push(`${speakerName}: ${text}`);
            }
        });

        return lines.length > 0 ? lines.join('\n') : container.innerText.trim();
    }

    /**
     * Handle Summarize Audio button click
     */
    async function handleSummarizeAudioClick() {
        if (!currentTranscript) {
            showAlert('No transcript available to summarize', 'warning');
            return;
        }
        
        try {
            // Show processing status
            document.getElementById('summaryProcessingStatus').classList.remove('d-none');
            document.getElementById('resultsSection').classList.add('d-none');
            updateSummaryProgress(10, 'Starting summarization with updated transcript...');
            
            // Extract live updated transcript from UI DOM containing human edits & auto-corrections
            const updatedTranscriptText = extractEditedTranscriptFromDOM('transcriptPreviewText') || currentTranscript.formatted_transcript.join('\n');
            console.log("Sending updated live transcript to LLM:", updatedTranscriptText);

            // Extract participants (speakers) from transcript text (user-edited names)
            const editedParticipants = extractParticipantsFromEditedText(updatedTranscriptText);
            const speakers = new Set(editedParticipants);
            if (speakers.size === 0 && currentTranscript.transcript) {
                currentTranscript.transcript.forEach(segment => {
                    speakers.add(`Speaker ${segment.speaker}`);
                });
            }
            
            // Get additional context if provided
            let additionalContext = null;
            const contextInput = document.getElementById('meetingContext');
            
            if (contextInput) {
                additionalContext = contextInput.value.trim();
                console.log("Including additional context:", additionalContext);
            }
            
            // Prepare request data with the UPDATED transcript and UPDATED speaker names
            const requestData = {
                transcript: updatedTranscriptText,
                participants: Array.from(speakers),
                language: currentTranscript.language,
                is_long_recording: document.getElementById('isLongRecording') ? document.getElementById('isLongRecording').checked : false,
                additional_context: additionalContext
            };
            
            // Submit the request
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            // Start polling for status updates
            startSummaryJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error starting summarization:', error);
            updateSummaryProgress(0, `Error: ${error.message}`, true);
        }
    }
    
    /**
     * Handle paste text form submission
     */
    async function handlePasteTextFormSubmit(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const transcript = formData.get('transcript');
        
        if (!transcript) {
            showAlert('Please enter a transcript', 'danger');
            return;
        }
        
        try {
            // First detect participants if not provided
            let participants = formData.get('participants');
            
            if (!participants) {
                const participantsResponse = await fetch('/api/extract-participants', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ transcript })
                });
                
                if (!participantsResponse.ok) {
                    throw new Error(`Server responded with ${participantsResponse.status}`);
                }
                
                participants = await participantsResponse.json();
            } else {
                participants = participants.split(',').map(p => p.trim()).filter(p => p);
            }
            
            // Show processing status
            document.getElementById('summaryProcessingStatus').classList.remove('d-none');
            document.getElementById('resultsSection').classList.add('d-none');
            updateSummaryProgress(10, 'Starting summarization...');
            
            // Prepare request data
            const requestData = {
                transcript: transcript,
                participants: participants,
                language: formData.get('language') || null,
                is_long_recording: false
            };
            
            // Store transcript for download
            currentTranscript = {
                formatted_transcript: transcript.split('\n')
            };
            
            // Submit the request
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            // Start polling for status updates
            startSummaryJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error processing text:', error);
            updateSummaryProgress(0, `Error: ${error.message}`, true);
        }
    }
    
    /**
     * Handle upload text form submission
     */
    async function handleUploadTextFormSubmit(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const textFile = formData.get('file');
        
        if (!textFile || textFile.size === 0) {
            showAlert('Please select a text file to upload', 'danger');
            return;
        }
        
        try {
            // Upload the text file
            const uploadResponse = await fetch('/api/upload-text', {
                method: 'POST',
                body: formData
            });
            
            if (!uploadResponse.ok) {
                throw new Error(`Server responded with ${uploadResponse.status}: ${await uploadResponse.text()}`);
            }
            
            const uploadData = await uploadResponse.json();
            const transcript = uploadData.transcript;
            
            // Display preview
            const previewText = document.getElementById('textPreviewContent');
            previewText.textContent = transcript.length > 1000 
                ? transcript.substring(0, 1000) + '...' 
                : transcript;
            
            document.getElementById('textPreview').classList.remove('d-none');
            
            // Show detected participants
            const participantsEl = document.getElementById('detectedParticipants');
            if (uploadData.participants && uploadData.participants.length > 0) {
                participantsEl.textContent = `✅ Detected participants: ${uploadData.participants.join(', ')}`;
            } else {
                participantsEl.textContent = '';
            }
            
            // Store transcript for later use
            currentTranscript = {
                formatted_transcript: transcript.split('\n')
            };
            
            // Store participants
            document.getElementById('uploadParticipants').value = uploadData.participants.join(', ');
            
        } catch (error) {
            console.error('Error uploading text file:', error);
            showAlert(`Error uploading text file: ${error.message}`, 'danger');
        }
    }
    
    /**
     * Handle summarize text button click
     */
    async function handleSummarizeTextClick() {
        try {
            // Get participants
            let participants = document.getElementById('uploadParticipants').value;
            
            if (!participants) {
                showAlert('Please enter participants', 'warning');
                return;
            }
            
            participants = participants.split(',').map(p => p.trim()).filter(p => p);
            
            // Show processing status
            document.getElementById('summaryProcessingStatus').classList.remove('d-none');
            document.getElementById('resultsSection').classList.add('d-none');
            updateSummaryProgress(10, 'Starting summarization...');
            
            // Get the transcript
            const transcript = currentTranscript.formatted_transcript.join('\n');
            
            // Prepare request data
            const requestData = {
                transcript: transcript,
                participants: participants,
                language: document.getElementById('uploadLanguage').value || null,
                is_long_recording: false
            };
            
            // Submit the request
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            // Start polling for status updates
            startSummaryJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error starting summarization:', error);
            updateSummaryProgress(0, `Error: ${error.message}`, true);
        }
    }
    
    /**
     * Poll for summary job status
     */
    function startSummaryJobPolling(jobId) {
        clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/job/${jobId}`);
                
                if (!response.ok) {
                    throw new Error(`Server responded with ${response.status}`);
                }
                
                const data = await response.json();
                
                // Update progress
                updateSummaryProgress(data.progress || 0, data.message || 'Processing...');
                
                // Check if job is complete
                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    
                    // Display results
                    if (data.result) {
                        currentResult = data.result;
                        displayResults(data.result);
                    }
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    updateSummaryProgress(0, `Error: ${data.message}`, true);
                }
                
            } catch (error) {
                console.error('Error polling job status:', error);
                clearInterval(pollInterval);
                updateSummaryProgress(0, `Error checking job status: ${error.message}`, true);
            }
        }, 1000);
    }
    
    /**
     * Update summary processing progress
     */
    function updateSummaryProgress(progress, message, isError = false) {
        const progressBar = document.getElementById('summaryProgressBar');
        const statusText = document.getElementById('summaryStatusText');
        
        progressBar.style.width = `${progress}%`;
        statusText.textContent = message;
        
        if (isError) {
            progressBar.classList.remove('bg-primary');
            progressBar.classList.add('bg-danger');
        } else {
            progressBar.classList.remove('bg-danger');
            progressBar.classList.add('bg-primary');
        }
    }
    
    /**
     * Add detailed confidence metrics for a speaker
     */
    function addSpeakerConfidenceDetails(speaker, result) {
        const speakerKey = speaker.replace("Speaker ", "");
        let metrics = null;
        
        // Try to get metrics from result first
        if (result.speaker_confidence_metrics && result.speaker_confidence_metrics[speakerKey]) {
            metrics = result.speaker_confidence_metrics[speakerKey];
        }
        // Fall back to currentTranscript if available
        else if (currentTranscript && currentTranscript.speaker_confidence_metrics && 
                 currentTranscript.speaker_confidence_metrics[speakerKey]) {
            metrics = currentTranscript.speaker_confidence_metrics[speakerKey];
        }
        
        if (!metrics) return '';
        
        // Create a progress bar for visual representation
        const progressBarClass = metrics.average_confidence >= 90 ? 'bg-success' : 
                               (metrics.average_confidence >= 70 ? 'bg-warning' : 'bg-danger');
        
        return `
            <div class="mt-3">
                <h6>Confidence Metrics:</h6>
                <div class="progress mb-2" style="height: 20px;">
                    <div class="progress-bar ${progressBarClass}" role="progressbar" 
                        style="width: ${metrics.average_confidence}%" 
                        aria-valuenow="${metrics.average_confidence}" 
                        aria-valuemin="0" aria-valuemax="100">
                        ${metrics.average_confidence.toFixed(1)}%
                    </div>
                </div>
                <div class="small text-muted">
                    <p class="mb-1"><strong>Average:</strong> ${metrics.average_confidence.toFixed(1)}%</p>
                    <p class="mb-1"><strong>Range:</strong> ${metrics.min_confidence.toFixed(1)}% - ${metrics.max_confidence.toFixed(1)}%</p>
                    ${metrics.low_confidence_segments > 0 ? 
                        `<p class="mb-1 text-warning">
                            <strong>Low Confidence Segments:</strong> ${metrics.low_confidence_segments}
                            (${((metrics.low_confidence_segments / metrics.total_segments) * 100).toFixed(1)}%)
                        </p>` : ''}
                </div>
            </div>
        `;
    }

    /**
     * Display results in the UI
     */
    function displayResults(result) {
        if (!result) return;

        // Hide processing status and show results section
        document.getElementById('summaryProcessingStatus').classList.add('d-none');
        document.getElementById('resultsSection').classList.remove('d-none');
        
        // Extract meeting summary string safely
        let summaryText = "";
        let keyPointsList = [];
        let decisionsList = [];

        if (typeof result.meeting_summary === 'string') {
            summaryText = result.meeting_summary;
        } else if (result.meeting_summary && typeof result.meeting_summary === 'object') {
            summaryText = result.meeting_summary.summary || result.meeting_summary.text || result.meeting_summary.overview || "";
            keyPointsList = Array.isArray(result.meeting_summary.key_points) ? result.meeting_summary.key_points : (Array.isArray(result.key_points) ? result.key_points : []);
            decisionsList = Array.isArray(result.meeting_summary.decisions) ? result.meeting_summary.decisions : (Array.isArray(result.decisions) ? result.decisions : []);
        }

        if (keyPointsList.length === 0 && Array.isArray(result.key_points)) {
            keyPointsList = result.key_points;
        }
        if (decisionsList.length === 0 && Array.isArray(result.decisions)) {
            decisionsList = result.decisions;
        }

        // 1. Meeting Summary
        const meetingSummary = document.getElementById('meetingSummary');
        if (meetingSummary) {
            meetingSummary.textContent = summaryText || "Summary generated successfully.";
            
            if (currentTranscript && currentTranscript.confidence_metrics) {
                const metrics = currentTranscript.confidence_metrics;
                const confidenceData = document.createElement('div');
                confidenceData.className = 'small text-muted mt-2';
                confidenceData.innerHTML = `
                    <strong>Transcription Confidence:</strong> ${metrics.average}% average
                    ${metrics.low_confidence_percentage > 10 ? 
                    `<span class="text-warning ms-2">⚠️ ${metrics.low_confidence_percentage}% low confidence segments</span>` : ''}
                `;
                meetingSummary.appendChild(confidenceData);
            }
        }

        // 2. Key Points
        const keyPoints = document.getElementById('keyPoints');
        if (keyPoints) {
            keyPoints.innerHTML = '';
            if (keyPointsList.length > 0) {
                keyPointsList.forEach(point => {
                    const li = document.createElement('li');
                    li.textContent = typeof point === 'string' ? point : (point.point || point.text || JSON.stringify(point));
                    keyPoints.appendChild(li);
                });
            } else {
                keyPoints.innerHTML = '<li class="text-muted">No key points extracted.</li>';
            }
        }
        
        // 3. Decisions
        const decisions = document.getElementById('decisions');
        if (decisions) {
            decisions.innerHTML = '';
            if (decisionsList.length > 0) {
                decisionsList.forEach(decision => {
                    const li = document.createElement('li');
                    li.textContent = typeof decision === 'string' ? decision : (decision.decision || decision.text || JSON.stringify(decision));
                    decisions.appendChild(li);
                });
            } else {
                decisions.innerHTML = '<li class="text-muted">No explicit decisions recorded during this meeting.</li>';
            }
        }
        
        // 4. Action Items
        const actionItems = document.getElementById('actionItems');
        if (actionItems) {
            actionItems.innerHTML = '';
            const actionsList = Array.isArray(result.action_items) ? result.action_items : (Array.isArray(result.actions) ? result.actions : []);
            
            if (actionsList.length > 0) {
                actionsList.forEach((item, index) => {
                    const actionId = `action-${index}`;
                    
                    let actionText = "";
                    let assignee = "Unassigned";
                    let dueDate = "Not specified";
                    let priority = "medium";

                    if (typeof item === 'string') {
                        actionText = item;
                    } else if (item && typeof item === 'object') {
                        actionText = item.action || item.item || item.task || item.description || JSON.stringify(item);
                        assignee = item.assignee || item.owner || item.person || "Unassigned";
                        dueDate = item.due_date || item.deadline || item.due || "Not specified";
                        priority = item.priority || "medium";
                    }

                    let priorityBadge = '<span class="badge bg-warning text-dark ms-2">Medium</span>';
                    if (String(priority).toLowerCase() === 'high') {
                        priorityBadge = '<span class="badge bg-danger ms-2">High</span>';
                    } else if (String(priority).toLowerCase() === 'low') {
                        priorityBadge = '<span class="badge bg-success ms-2">Low</span>';
                    }
                    
                    const actionItemHtml = `
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="heading-${actionId}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${actionId}" aria-expanded="false" aria-controls="collapse-${actionId}">
                                    <strong>${actionText}</strong>${priorityBadge}
                                </button>
                            </h2>
                            <div id="collapse-${actionId}" class="accordion-collapse collapse" aria-labelledby="heading-${actionId}" data-bs-parent="#actionItems">
                                <div class="accordion-body">
                                    <p><strong>Assignee:</strong> ${assignee}</p>
                                    <p><strong>Due Date:</strong> ${dueDate}</p>
                                </div>
                            </div>
                        </div>
                    `;
                    actionItems.innerHTML += actionItemHtml;
                });
            } else {
                actionItems.innerHTML = '<p class="text-muted p-2">No explicit action items assigned during this meeting.</p>';
            }
        }
        
        // 5. Metadata
        const metadataTable = document.getElementById('metadataTable');
        if (metadataTable) {
            metadataTable.innerHTML = '';
            if (result.metadata) {
                const metadata = result.metadata;
                if (metadata.language_name) {
                    addMetadataRow(metadataTable, 'Language', metadata.language_name);
                } else {
                    addMetadataRow(metadataTable, 'Language', metadata.language || 'Auto-detected');
                }
                
                if (currentTranscript && currentTranscript.confidence_metrics) {
                    const metrics = currentTranscript.confidence_metrics;
                    addMetadataRow(metadataTable, 'Transcription Confidence', `${metrics.average}% (range: ${metrics.min}%-${metrics.max}%)`);
                    if (metrics.low_confidence_percentage > 10) {
                        addMetadataRow(metadataTable, 'Low Confidence Segments', `${metrics.low_confidence_count} segments (${metrics.low_confidence_percentage}%)`);
                    }
                }
                if (metadata.total_duration_minutes) {
                    addMetadataRow(metadataTable, 'Duration', `${metadata.total_duration_minutes} minutes`);
                }
                if (metadata.participant_count) {
                    addMetadataRow(metadataTable, 'Participants', metadata.participant_count);
                }
                if (metadata.chunks_analyzed) {
                    addMetadataRow(metadataTable, 'Chunks Analyzed', metadata.chunks_analyzed);
                }
            }
        }
        
        // 6. Speaker Summaries
        const speakerSummaries = document.getElementById('speakerSummaries');
        if (speakerSummaries) {
            speakerSummaries.innerHTML = '';
            const spkSummDict = result.speaker_summaries || result.speaker_summary || {};
            const entries = Object.entries(spkSummDict);
            
            if (entries.length > 0) {
                entries.forEach(([speaker, summary], index) => {
                    const speakerId = `speaker-${index}`;
                    let briefSummary = "";
                    let contributionsList = "";
                    let actionsList = "";
                    let questionsList = "";

                    if (typeof summary === 'string') {
                        briefSummary = summary;
                    } else if (summary && typeof summary === 'object') {
                        briefSummary = summary.brief_summary || summary.summary || summary.text || "";
                        
                        if (Array.isArray(summary.key_contributions) && summary.key_contributions.length > 0) {
                            contributionsList = '<h6>Key Contributions:</h6><ul>' + 
                                summary.key_contributions.map(c => `<li>${typeof c === 'string' ? c : (c.text || JSON.stringify(c))}</li>`).join('') + 
                                '</ul>';
                        }
                        if (Array.isArray(summary.action_items) && summary.action_items.length > 0) {
                            actionsList = '<h6>Action Items:</h6><ul>' + 
                                summary.action_items.map(a => `<li>${typeof a === 'string' ? a : (a.action || a.text || JSON.stringify(a))}</li>`).join('') + 
                                '</ul>';
                        }
                        if (Array.isArray(summary.questions_raised) && summary.questions_raised.length > 0) {
                            questionsList = '<h6>Questions Raised:</h6><ul>' + 
                                summary.questions_raised.map(q => `<li>${typeof q === 'string' ? q : (q.question || q.text || JSON.stringify(q))}</li>`).join('') + 
                                '</ul>';
                        }
                    }
                    
                    const speakerItemHtml = `
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="heading-${speakerId}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${speakerId}" aria-expanded="false" aria-controls="collapse-${speakerId}">
                                    <strong>${speaker}</strong>
                                </button>
                            </h2>
                            <div id="collapse-${speakerId}" class="accordion-collapse collapse" aria-labelledby="heading-${speakerId}" data-bs-parent="#speakerSummaries">
                                <div class="accordion-body">
                                    <p><strong>Summary:</strong> ${briefSummary || 'No summary available.'}</p>
                                    ${contributionsList}
                                    ${actionsList}
                                    ${questionsList}
                                </div>
                            </div>
                        </div>
                    `;
                    speakerSummaries.innerHTML += speakerItemHtml;
                });
            } else {
                speakerSummaries.innerHTML = '<p class="text-muted p-2">No speaker-specific summaries generated.</p>';
            }
        }
    }

    // New helper function to add detailed speaker confidence metrics
    function addSpeakerConfidenceDetails(speaker, result) {
        // Extract speaker ID (remove "Speaker " prefix if present)
        const speakerId = speaker.replace("Speaker ", "");
        
        // Look for speaker confidence metrics in the result first
        if (result.speaker_confidence_metrics && result.speaker_confidence_metrics[speakerId]) {
            const metrics = result.speaker_confidence_metrics[speakerId];
            
            // Create confidence indicator class based on level
            const confidenceClass = metrics.confidence_level === 'high' ? 'text-success' : 
                                (metrics.confidence_level === 'medium' ? 'text-warning' : 'text-danger');
            
            return `
                <div class="mt-3 small">
                    <h6>Transcription Confidence:</h6>
                    <div class="row">
                        <div class="col-6">
                            <span class="${confidenceClass}"><strong>${metrics.average_confidence}%</strong></span> average
                        </div>
                        <div class="col-6">
                            <span>Range: ${metrics.min_confidence}% - ${metrics.max_confidence}%</span>
                        </div>
                    </div>
                    <div class="progress mt-1 mb-2" style="height: 8px;">
                        <div class="progress-bar ${metrics.confidence_level === 'high' ? 'bg-success' : 
                                            (metrics.confidence_level === 'medium' ? 'bg-warning' : 'bg-danger')}" 
                            role="progressbar" style="width: ${metrics.average_confidence}%" 
                            aria-valuenow="${metrics.average_confidence}" aria-valuemin="0" aria-valuemax="100">
                        </div>
                    </div>
                    <span class="small text-muted">Based on ${metrics.segment_count} segments</span>
                </div>
            `;
        }
        // Fallback to checking currentTranscript if available
        else if (currentTranscript && currentTranscript.speaker_confidence_metrics && 
                currentTranscript.speaker_confidence_metrics[speakerId]) {
            
            const metrics = currentTranscript.speaker_confidence_metrics[speakerId];
            
            // Create confidence indicator class based on level
            const confidenceClass = metrics.confidence_level === 'high' ? 'text-success' : 
                                (metrics.confidence_level === 'medium' ? 'text-warning' : 'text-danger');
            
            return `
                <div class="mt-3 small">
                    <h6>Transcription Confidence:</h6>
                    <div class="row">
                        <div class="col-6">
                            <span class="${confidenceClass}"><strong>${metrics.average_confidence}%</strong></span> average
                        </div>
                        <div class="col-6">
                            <span>Range: ${metrics.min_confidence}% - ${metrics.max_confidence}%</span>
                        </div>
                    </div>
                    <div class="progress mt-1 mb-2" style="height: 8px;">
                        <div class="progress-bar ${metrics.confidence_level === 'high' ? 'bg-success' : 
                                            (metrics.confidence_level === 'medium' ? 'bg-warning' : 'bg-danger')}" 
                            role="progressbar" style="width: ${metrics.average_confidence}%" 
                            aria-valuenow="${metrics.average_confidence}" aria-valuemin="0" aria-valuemax="100">
                        </div>
                    </div>
                    <span class="small text-muted">Based on ${metrics.segment_count} segments</span>
                </div>
            `;
        }
        
        // Return empty string if no confidence metrics available
        return '';
    }
    
    /**
     * Add a row to the metadata table
     */
    function addMetadataRow(table, label, value) {
        const row = table.insertRow();
        const labelCell = row.insertCell(0);
        const valueCell = row.insertCell(1);
        
        labelCell.innerHTML = `<strong>${label}:</strong>`;
        valueCell.textContent = value;
    }
    
    /**
     * Handle download JSON button click
     */
    function handleDownloadJson() {
        if (!currentResult) {
            showAlert('No results available to download', 'warning');
            return;
        }
        
        // Create a Blob with the JSON data
        const jsonBlob = new Blob([JSON.stringify(currentResult, null, 2)], { type: 'application/json' });
        
        // Create a download link
        const url = URL.createObjectURL(jsonBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'meeting_summary.json';
        
        // Trigger download
        document.body.appendChild(a);
        a.click();
        
        // Clean up
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 0);
    }
    
    /**
     * Handle download text button click
     */
    function handleDownloadText() {
        if (!currentTranscript || !currentTranscript.formatted_transcript) {
            showAlert('No transcript available to download', 'warning');
            return;
        }
        
        // Create a Blob with the text data
        const textBlob = new Blob([currentTranscript.formatted_transcript.join('\n')], { type: 'text/plain' });
        
        // Create a download link
        const url = URL.createObjectURL(textBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'meeting_transcript.txt';
        
        // Trigger download
        document.body.appendChild(a);
        a.click();
        
        // Clean up
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 0);
    }
    
    /**
     * Show an alert message
     */
    function showAlert(message, type = 'info') {
        // Create alert element
        const alertEl = document.createElement('div');
        alertEl.className = `alert alert-${type} alert-dismissible fade show`;
        alertEl.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Insert at the top of the container
        const container = document.querySelector('.container');
        container.insertBefore(alertEl, container.firstChild);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alertEl.parentNode) {
                alertEl.classList.remove('show');
                setTimeout(() => alertEl.remove(), 150);
            }
        }, 5000);
    }

    // Add this function somewhere in your main.js
    function getLanguageDisplayName(languageCode) {
        const languageMap = {
            "en": "English",
            "hi": "Hindi", 
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "zh": "Chinese",
            "ja": "Japanese",
            "ru": "Russian",
            "ar": "Arabic",
            "auto": "Auto-detected"
        };
        
        return languageMap[languageCode] || languageCode;
    }

    // ── Live Recording Feature ──
    let mediaRecorder = null;
    let audioChunks = [];
    let recordTimerInterval = null;
    let recordStartTime = null;
    let recordedAudioBlob = null;
    let realtimeWebSocket = null;

    const startRecordBtn = document.getElementById('startRecordBtn');
    const stopRecordBtn = document.getElementById('stopRecordBtn');
    const recordingTimer = document.getElementById('recordingTimer');
    const recordStatus = document.getElementById('recordStatus');
    const recordPlaybackSection = document.getElementById('recordPlaybackSection');
    const recordedAudioPlayback = document.getElementById('recordedAudioPlayback');
    const processRecordedBtn = document.getElementById('processRecordedBtn');
    const summarizeRecordedBtn = document.getElementById('summarizeRecordedBtn');

    if (startRecordBtn) {
        startRecordBtn.addEventListener('click', startRecording);
    }
    if (stopRecordBtn) {
        stopRecordBtn.addEventListener('click', stopRecording);
    }
    if (processRecordedBtn) {
        processRecordedBtn.addEventListener('click', processRecordedAudio);
    }
    if (summarizeRecordedBtn) {
        summarizeRecordedBtn.addEventListener('click', handleSummarizeRecordedClick);
    }
    const refineRecordBtn = document.getElementById('refineRecordTranscriptBtn');
    if (refineRecordBtn) {
        refineRecordBtn.addEventListener('click', handleRefineTranscriptClick);
    }


    function getMicrophoneStream() {
        if (typeof navigator !== 'undefined' && navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function') {
            return navigator.mediaDevices.getUserMedia({ audio: true });
        }
        const nav = (typeof navigator !== 'undefined') ? navigator : null;
        const legacyGetUserMedia = nav ? (nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia || nav.msGetUserMedia) : null;
        if (typeof legacyGetUserMedia === 'function') {
            return new Promise((resolve, reject) => {
                legacyGetUserMedia.call(nav, { audio: true }, resolve, reject);
            });
        }
        if (typeof window !== 'undefined' && !window.isSecureContext && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
            throw new Error('Microphone access is blocked over non-secure HTTP IP addresses. Please open http://localhost:8000 in your browser address bar.');
        }
        throw new Error('Microphone permission or navigator.mediaDevices is blocked by your browser settings. Please allow microphone access in your browser site settings.');
    }

    let audioContext = null;
    let audioSource = null;
    let audioProcessorNode = null;

    async function startRecording() {
        audioChunks = [];
        if (recordPlaybackSection) recordPlaybackSection.classList.add('d-none');
        const procStatus = document.getElementById('recordProcessingStatus');
        if (procStatus) procStatus.classList.add('d-none');
        const trPreview = document.getElementById('recordTranscriptPreview');
        if (trPreview) trPreview.classList.add('d-none');
        
        const liveContainer = document.getElementById('liveStreamContainer');
        const liveBadge = document.getElementById('liveBadge');
        const liveContent = document.getElementById('liveStreamContent');
        const liveStatus = document.getElementById('liveStreamStatus');

        if (liveContainer) liveContainer.classList.remove('d-none');
        if (liveBadge) liveBadge.classList.remove('d-none');
        if (liveContent) liveContent.innerHTML = '<em class="text-muted">Connecting live WebSocket stream... Speak into microphone.</em>';
        if (liveStatus) liveStatus.innerText = 'Connecting...';

        const lang = document.getElementById('recordLanguage') ? document.getElementById('recordLanguage').value : 'auto';
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/realtime-audio?language=${lang}`;

        try {
            const stream = await getMicrophoneStream();

            realtimeWebSocket = new WebSocket(wsUrl);

            realtimeWebSocket.onopen = () => {
                if (liveStatus) liveStatus.innerText = 'Live stream active. Listening...';
                if (recordStatus) recordStatus.innerText = '⚡ Real-time audio streaming active! Speak into microphone.';
            };

            realtimeWebSocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'live_update' && data.segments) {
                        renderLiveStreamSegments(data.segments);
                    } else if (data.type === 'final_result' && data.result) {
                        currentJobId = data.result.job_id;
                        currentTranscript = data.result;
                        if (trPreview) trPreview.classList.remove('d-none');
                        if (data.result.raw_transcription) {
                            renderInteractiveTranscript(data.result.raw_transcription, 'recordTranscriptPreviewText');
                        }
                        // Only close now that the final transcript has actually arrived —
                        // closing on a fixed timer risked cutting the connection before
                        // the server finished saving/sending it.
                        if (realtimeWebSocket) realtimeWebSocket.close();
                    }
                } catch (err) {
                    console.error("Error parsing WebSocket message:", err);
                }
            };

            realtimeWebSocket.onerror = (err) => {
                console.error("WebSocket error:", err);
                if (liveStatus) liveStatus.innerText = 'Stream error';
            };
            
            // Setup Web Audio API PCM 16kHz Streamer for WebSockets
            try {
                audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
                audioSource = audioContext.createMediaStreamSource(stream);
                audioProcessorNode = audioContext.createScriptProcessor(4096, 1, 1);

                audioProcessorNode.onaudioprocess = (e) => {
                    if (!realtimeWebSocket || realtimeWebSocket.readyState !== WebSocket.OPEN) return;
                    const inputData = e.inputBuffer.getChannelData(0);
                    const pcm16 = new Int16Array(inputData.length);
                    for (let i = 0; i < inputData.length; i++) {
                        let s = Math.max(-1, Math.min(1, inputData[i]));
                        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                    }
                    realtimeWebSocket.send(pcm16.buffer);
                };

                // Route through a silent gain node instead of straight to speakers —
                // ScriptProcessorNode needs a destination to fire onaudioprocess in some
                // browsers, but connecting directly to destination plays the mic input
                // back out loud, causing an acoustic feedback/echo loop that degrades
                // transcription accuracy when not using headphones.
                const silentGain = audioContext.createGain();
                silentGain.gain.value = 0;

                audioSource.connect(audioProcessorNode);
                audioProcessorNode.connect(silentGain);
                silentGain.connect(audioContext.destination);
            } catch (pcmErr) {
                console.warn("PCM AudioContext fallback:", pcmErr);
            }
            
            let mimeType = 'audio/webm';
            if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = 'audio/ogg';
            if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = 'audio/mp4';
            if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = '';
            
            const options = mimeType ? { mimeType } : {};
            mediaRecorder = new MediaRecorder(stream, options);
            
            mediaRecorder.addEventListener('dataavailable', async (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            });
            
            mediaRecorder.addEventListener('stop', () => {
                const extension = mimeType.includes('webm') ? 'webm' : (mimeType.includes('ogg') ? 'ogg' : (mimeType.includes('mp4') ? 'mp4' : 'wav'));
                recordedAudioBlob = new Blob(audioChunks, { type: mimeType || 'audio/wav' });
                
                const audioUrl = URL.createObjectURL(recordedAudioBlob);
                if (recordedAudioPlayback) recordedAudioPlayback.src = audioUrl;
                if (recordPlaybackSection) recordPlaybackSection.classList.remove('d-none');
                recordedAudioBlob.extension = extension;
                
                if (liveBadge) liveBadge.classList.add('d-none');
                if (liveStatus) liveStatus.innerText = 'Stream ended';
                if (recordStatus) recordStatus.innerText = 'Recording stopped. You can preview audio or summarize transcript.';
            });
            
            mediaRecorder.start(1000); 
            recordStartTime = Date.now();
            updateTimer();
            recordTimerInterval = setInterval(updateTimer, 1000);
            
            if (startRecordBtn) startRecordBtn.classList.add('d-none');
            if (stopRecordBtn) stopRecordBtn.classList.remove('d-none');
            
        } catch (error) {
            console.error('Error starting voice recording:', error);
            if (recordStatus) recordStatus.innerText = `Error: ${error.message}`;
            showAlert(`Could not access microphone: ${error.message}`, 'danger');
        }
    }

    function renderLiveStreamSegments(segments) {
        const container = document.getElementById('liveStreamContent');
        if (!container) return;
        if (!segments || segments.length === 0) {
            container.innerHTML = '<em class="text-muted">Listening... Speak into microphone.</em>';
            return;
        }
        let html = '';
        segments.forEach(seg => {
            const color = seg.color || '🔵';
            const speaker = seg.speaker || 'Speaker 1';
            const timeStr = seg.timestamp || '00:00';
            const text = seg.text || '';
            html += `<div class="mb-2 p-1 border-bottom border-secondary">
                <span style="font-size: 1.1rem;">${color}</span> 
                <strong class="text-info">${speaker}</strong> 
                <span class="badge bg-secondary ms-1 me-2">${timeStr}</span>
                <span>${text}</span>
            </div>`;
        });
        container.innerHTML = html;
        container.scrollTop = container.scrollHeight;
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
        if (audioProcessorNode) {
            try { audioProcessorNode.disconnect(); } catch (e) {}
            audioProcessorNode = null;
        }
        if (audioSource) {
            try { audioSource.disconnect(); } catch (e) {}
            audioSource = null;
        }
        if (audioContext) {
            try { audioContext.close(); } catch (e) {}
            audioContext = null;
        }
        if (realtimeWebSocket && realtimeWebSocket.readyState === WebSocket.OPEN) {
            realtimeWebSocket.send(JSON.stringify({ action: "STOP" }));
            // Don't force-close here — wait for the server's 'final_result' message
            // (handled in onmessage) so the transcript actually reaches the browser.
            // Fallback safety close in case the server never responds.
            setTimeout(() => {
                if (realtimeWebSocket && realtimeWebSocket.readyState === WebSocket.OPEN) {
                    realtimeWebSocket.close();
                }
            }, 30000);
        }
        clearInterval(recordTimerInterval);
        if (startRecordBtn) startRecordBtn.classList.remove('d-none');
        if (stopRecordBtn) stopRecordBtn.classList.add('d-none');
    }

    function updateTimer() {
        if (!recordingTimer) return;
        const elapsedMs = Date.now() - recordStartTime;
        const totalSecs = Math.floor(elapsedMs / 1000);
        const mins = Math.floor(totalSecs / 60).toString().padStart(2, '0');
        const secs = (totalSecs % 60).toString().padStart(2, '0');
        recordingTimer.innerText = `${mins}:${secs}`;
    }

    async function processRecordedAudio() {
        if (!recordedAudioBlob) {
            showAlert('No recorded audio blob found', 'warning');
            return;
        }
        
        const ext = recordedAudioBlob.extension || 'webm';
        const formData = new FormData();
        formData.append('file', recordedAudioBlob, `live_recording.${ext}`);
        formData.append('language', document.getElementById('recordLanguage').value);
        formData.append('is_long_recording', document.getElementById('recordIsLong') ? document.getElementById('recordIsLong').checked : false);
        
        try {
            const recordedUrl = URL.createObjectURL(recordedAudioBlob);
            window.currentAudioStreamUrl = recordedUrl;
            const recordedPlayer = document.getElementById('recordedAudioPlayback');
            if (recordedPlayer) {
                recordedPlayer.src = recordedUrl;
            }

            const procStatus = document.getElementById('recordProcessingStatus');
            if (procStatus) procStatus.classList.remove('d-none');
            updateRecordProgress(0, 'Starting recorded audio processing...');
            
            const response = await fetch('/api/upload-audio', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            startRecordJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error processing live recording:', error);
            updateRecordProgress(0, `Error: ${error.message}`, true);
        }
    }

    function updateRecordProgress(percent, message, isError = false) {
        const progressBar = document.getElementById('recordProgressBar');
        const statusText = document.getElementById('recordStatusText');
        
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
            if (isError) {
                progressBar.classList.add('bg-danger');
            } else {
                progressBar.classList.remove('bg-danger');
            }
        }
        if (statusText) {
            statusText.innerHTML = message;
        }
    }

    function startRecordJobPolling(jobId) {
        clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/job/${jobId}`);
                if (!response.ok) {
                    throw new Error(`Server responded with ${response.status}`);
                }
                
                const data = await response.json();
                updateRecordProgress(data.progress || 0, data.message || 'Processing...');
                
                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    if (data.result && data.result.transcript) {
                        currentTranscript = data.result;
                        
                        // Show preview
                        const trPreview = document.getElementById('recordTranscriptPreview');
                        if (trPreview) trPreview.classList.remove('d-none');
                        
                        if (data.result.segments && data.result.segments.length > 0) {
                            renderInteractiveTranscript(data.result.segments, 'recordTranscriptPreviewText');
                        } else if (data.result.raw_transcription) {
                            renderInteractiveTranscript(data.result.raw_transcription, 'recordTranscriptPreviewText');
                        } else {
                            let textContent = '';
                            currentTranscript.transcript.forEach(seg => {
                                textContent += `[${seg.start_time_formatted}] Speaker ${seg.speaker}: ${seg.text}\n`;
                            });
                            const trPreviewText = document.getElementById('recordTranscriptPreviewText');
                            if (trPreviewText) trPreviewText.innerText = textContent;
                        }
                        
                        let successMsg = `Processing complete. `;
                        const selectedLanguage = document.getElementById('recordLanguage').value;
                        const detectedLang = data.result.language;
                        if (selectedLanguage === 'auto') {
                            successMsg += `Language detected as: ${getLanguageDisplayName(detectedLang)}`;
                        }
                        
                        updateRecordProgress(100, successMsg);
                        showAlert('Recorded audio processed successfully!', 'success');
                    }
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    updateRecordProgress(0, `Failed: ${data.message || 'Unknown error'}`, true);
                    showAlert(`Processing failed: ${data.message}`, 'danger');
                }
            } catch (error) {
                console.error('Error polling status:', error);
            }
        }, 2000);
    }

    async function handleSummarizeRecordedClick() {
        if (!currentTranscript) {
            showAlert('No transcript available to summarize', 'warning');
            return;
        }
        
        try {
            document.getElementById('summaryProcessingStatus').classList.remove('d-none');
            document.getElementById('resultsSection').classList.add('d-none');
            updateSummaryProgress(10, 'Starting summarization with updated transcript...');
            
            // Extract live updated transcript from UI DOM containing human edits & auto-corrections
            const updatedTranscriptText = extractEditedTranscriptFromDOM('recordTranscriptPreviewText') || currentTranscript.formatted_transcript.join('\n');
            console.log("Sending updated recorded live transcript to LLM:", updatedTranscriptText);

            // Extract participants (speakers) from edited transcript text
            const editedParticipants = extractParticipantsFromEditedText(updatedTranscriptText);
            const speakers = new Set(editedParticipants);
            if (speakers.size === 0 && currentTranscript.transcript) {
                currentTranscript.transcript.forEach(segment => {
                    speakers.add(`Speaker ${segment.speaker}`);
                });
            }
            
            // Get additional context
            let additionalContext = null;
            const contextInput = document.getElementById('meetingContext');
            if (contextInput) {
                additionalContext = contextInput.value.trim();
            }
            
            const requestData = {
                transcript: updatedTranscriptText,
                participants: Array.from(speakers),
                language: currentTranscript.language,
                is_long_recording: document.getElementById('recordIsLong') ? document.getElementById('recordIsLong').checked : false,
                additional_context: additionalContext
            };
            
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}: ${await response.text()}`);
            }
            
            const data = await response.json();
            currentJobId = data.job_id;
            
            startSummaryJobPolling(currentJobId);
            
        } catch (error) {
            console.error('Error starting summarization:', error);
            updateSummaryProgress(0, `Error: ${error.message}`, true);
        }
    }
});