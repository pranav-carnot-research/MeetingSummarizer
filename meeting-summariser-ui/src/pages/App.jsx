import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Menu } from 'lucide-react';
import AudioUpload from '../components/inputs/AudioUpload.jsx';
import LiveRecording from '../components/inputs/LiveRecording.jsx';
import PasteText from '../components/inputs/PasteText.jsx';
import UploadText from '../components/inputs/UploadText.jsx';
import TranscriptPreview from '../components/TranscriptPreview.jsx';
import SummaryView from '../components/SummaryView.jsx';
import FollowUpEmails from '../components/FollowUpEmails.jsx';
import Sidebar from '../components/Sidebar.jsx';
import ResultsTabs from '../components/ResultsTabs.jsx';
import GenerateBar from '../components/GenerateBar.jsx';
import { AudioPlayerView, ConfidenceView } from '../components/ResultsViews.jsx';
import { Card, SectionTitle } from '../components/Card.jsx';
import {
  getLanguages, extractParticipants, summarize, pollJob,
} from '../api/client.js';

const INPUT_VIEWS = new Set(['audio', 'realtime', 'paste', 'text']);
const RESULT_VIEWS = new Set(['audio-player', 'transcript', 'confidence', 'report']);

// Normalise a raw diarization key (e.g. "SPEAKER_00", "Speaker_1", or a
// friendly rename like "Alice") into a participant display label.
// Prevents "Speaker SPEAKER_00" and similar double-prefixing.
function speakerLabel(raw) {
  const s = String(raw ?? '?').trim();
  const m = s.match(/^speaker[_\s-]*(.+)$/i);
  return m ? `Speaker ${m[1]}` : s;
}

export default function App() {
  const [activeView, setActiveView] = useState('audio'); // default landing view
  const [languages, setLanguages] = useState([{ code: 'auto', name: 'Auto-detect' }]);

  // Mobile-only drawer state. Desktop ignores this (CSS keeps the sidebar
  // in its always-visible column at >900px). Any nav interaction closes
  // the drawer so the newly-selected view is immediately visible.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = () => setSidebarOpen(false);
  const handleNavigate = (view) => { setActiveView(view); closeSidebar(); };

  // Transcript state — persisted across view switches
  const [transcript, setTranscript] = useState('');
  const [transcriptData, setTranscriptData] = useState(null);
  const [detectedLanguage, setDetectedLanguage] = useState(null);
  const [isLongRecording, setIsLongRecording] = useState(false);

  const [audioBlob, setAudioBlob] = useState(null);
  const audioUrl = useMemo(() => (audioBlob ? URL.createObjectURL(audioBlob) : null), [audioBlob]);
  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);

  const [participants, setParticipants] = useState('');
  const [additionalContext, setAdditionalContext] = useState('');

  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryProgress, setSummaryProgress] = useState(0);
  const [summaryStatus, setSummaryStatus] = useState('');
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);

  const hasTranscript = !!transcript.trim();
  const hasSummary = !!summary;

  useEffect(() => { getLanguages().then(setLanguages); }, []);

  // ── Input handlers ────────────────────────────────────────
  const afterTranscriptReady = () => {
    // Jump to Transcript & Playback so the user sees what was produced.
    setActiveView('transcript');
  };

  const handleTranscriptFromAudio = ({ transcript: t, transcriptData: td, language, audioBlob: blob }) => {
    setTranscript(t);
    setTranscriptData(td);
    setAudioBlob(blob || null);
    if (language) setDetectedLanguage(language);
    if (td?.transcript && Array.isArray(td.transcript)) {
      const speakers = new Set();
      td.transcript.forEach((seg) => {
        if (seg.speaker !== undefined) speakers.add(speakerLabel(seg.speaker));
      });
      if (speakers.size) setParticipants([...speakers].sort().join(', '));
    }
    afterTranscriptReady();
  };

  const handleTranscriptFromText = async (text) => {
    setTranscript(text);
    setTranscriptData(null);
    setAudioBlob(null);
    if (text?.trim()) {
      try {
        const detected = await extractParticipants(text);
        if (detected?.length) setParticipants(detected.join(', '));
      } catch { /* non-fatal */ }
    }
  };

  const handleTextLoaded = ({ transcript: t, participants: p }) => {
    setTranscript(t);
    setTranscriptData(null);
    setAudioBlob(null);
    if (p?.length) setParticipants(p.join(', '));
    afterTranscriptReady();
  };

  const handleTranscriptEdit = (flatText, updatedData) => {
    setTranscript(flatText);
    setTranscriptData(updatedData);
    if (Array.isArray(updatedData?.transcript)) {
      const speakers = new Set();
      updatedData.transcript.forEach((seg) => {
        if (seg.speaker !== undefined) speakers.add(speakerLabel(seg.speaker));
      });
      if (speakers.size) setParticipants([...speakers].sort().join(', '));
    }
  };

  const canSubmit = !!transcript.trim() && !!participants.trim();

  const doSummarize = async () => {
    if (!canSubmit) return;
    setSummaryBusy(true);
    setSummaryError(null);
    setSummary(null);
    setSummaryProgress(0);
    setSummaryStatus('Submitting…');
    try {
      const { job_id } = await summarize({
        transcript,
        participants,
        language: detectedLanguage || null,
        isLongRecording,
        additionalContext,
      });
      const final = await pollJob(job_id, {
        onUpdate: (s) => {
          setSummaryProgress(s.progress || 0);
          setSummaryStatus(s.status_message || s.status || 'Processing…');
        },
      });
      setSummary(final.result || final);
      setActiveView('report');
    } catch (e) {
      setSummaryError(e.message || 'Summary generation failed');
    } finally {
      setSummaryBusy(false);
    }
  };

  const resetSession = () => {
    if (hasTranscript || hasSummary) {
      const ok = window.confirm('Discard the current transcript and summary, and start a new session?');
      if (!ok) return;
    }
    setTranscript('');
    setTranscriptData(null);
    setAudioBlob(null);
    setDetectedLanguage(null);
    setIsLongRecording(false);
    setParticipants('');
    setAdditionalContext('');
    setSummary(null);
    setSummaryError(null);
    setSummaryProgress(0);
    setSummaryStatus('');
    setActiveView('audio');
  };

  // Guard: if a result view is active but its data disappears, bounce back.
  useEffect(() => {
    if (RESULT_VIEWS.has(activeView) && !hasTranscript) setActiveView('audio');
    if (activeView === 'report' && !hasSummary) setActiveView('transcript');
  }, [activeView, hasTranscript, hasSummary]);

  return (
    <div style={{ background: '#ffffff', minHeight: '100vh' }}>
      {/* Mobile top bar — hamburger + wordmark. Hidden on desktop via CSS.
          Sits inside the flow so the main content pushes down under it. */}
      <div className="app-mobile-menubar">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open menu"
          className="app-mobile-menubtn"
        >
          <Menu size={20} />
        </button>
        <div className="app-mobile-wordmark">Meeting Summariser</div>
      </div>

      {/* Drawer scrim. `is-open` reveals it; click closes the drawer.
          Hidden on desktop by CSS since the sidebar is always visible there. */}
      <div
        className={`app-sidebar-backdrop${sidebarOpen ? ' is-open' : ''}`}
        onClick={closeSidebar}
        aria-hidden="true"
      />

      <div className="app-shell" style={{ display: 'flex', alignItems: 'stretch' }}>
        <Sidebar
          activeView={activeView}
          onNavigate={handleNavigate}
          hasResults={hasTranscript}
          onNewSession={() => { resetSession(); closeSidebar(); }}
          onReturnToResults={() => {
            setActiveView(hasSummary ? 'report' : 'transcript');
            closeSidebar();
          }}
          open={sidebarOpen}
          onClose={closeSidebar}
        />

        {/* MAIN PANE */}
        <main className="app-main" style={{ flex: 1, minWidth: 0, padding: '32px 40px 60px' }}>
          <ViewHeader
            activeView={activeView}
            hasResults={hasTranscript}
            onReturnToResults={() => setActiveView(hasSummary ? 'report' : 'transcript')}
          />

          {/* Horizontal result tabs — only shown while the user is inside the
              results workspace (any of the 4 result views). */}
          {RESULT_VIEWS.has(activeView) && (
            <ResultsTabs
              activeView={activeView}
              onNavigate={setActiveView}
              hasSummary={hasSummary}
            />
          )}

          {/* Input views */}
          {activeView === 'audio' && (
            <AudioUpload languages={languages} onComplete={handleTranscriptFromAudio} />
          )}
          {activeView === 'realtime' && (
            <LiveRecording languages={languages} onComplete={handleTranscriptFromAudio} />
          )}
          {activeView === 'paste' && (
            <>
              <PasteText onChange={handleTranscriptFromText} />
              {hasTranscript && (
                <div style={{ marginTop: 12, textAlign: 'right' }}>
                  <button onClick={afterTranscriptReady} style={primaryBtn}>Continue →</button>
                </div>
              )}
            </>
          )}
          {activeView === 'text' && (
            <UploadText onLoaded={handleTextLoaded} />
          )}

          {/* Result views */}
          {activeView === 'audio-player' && (
            <AudioPlayerView audioBlob={audioBlob} audioUrl={audioUrl} />
          )}

          {activeView === 'transcript' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <GenerateBar
                participants={participants}
                onParticipantsChange={setParticipants}
                context={additionalContext}
                onContextChange={setAdditionalContext}
                isLongRecording={isLongRecording}
                onLongRecordingChange={setIsLongRecording}
                onSubmit={doSummarize}
                canSubmit={canSubmit}
                busy={summaryBusy}
                progress={summaryProgress}
                statusMessage={summaryStatus}
                hasSummary={hasSummary}
              />
              {summaryError && (
                <div style={errorBox}>{summaryError}</div>
              )}
              {transcriptData?.transcript?.length > 0 ? (
                <TranscriptPreview
                  transcriptData={transcriptData}
                  audioSrc={audioUrl}
                  onTranscriptChange={handleTranscriptEdit}
                />
              ) : (
                <Card>
                  <SectionTitle subtitle="Edit directly — participants and the generated summary use this text.">
                    Transcript ({transcript.length.toLocaleString()} chars)
                  </SectionTitle>
                  <textarea
                    value={transcript}
                    onChange={(e) => setTranscript(e.target.value)}
                    style={{
                      width: '100%', minHeight: 300, padding: 12, borderRadius: 10,
                      border: '1px solid #cbd5e1', background: '#f8fafc',
                      fontFamily: 'ui-monospace, SFMono-Regular, monospace', fontSize: 12.5,
                      lineHeight: 1.6, whiteSpace: 'pre-wrap', color: '#333',
                      resize: 'vertical', outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </Card>
              )}
            </div>
          )}

          {activeView === 'confidence' && (
            <ConfidenceView
              transcriptData={transcriptData}
              onOpenTranscript={() => setActiveView('transcript')}
            />
          )}

          {activeView === 'report' && hasSummary && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <SummaryView summary={summary} transcript={transcript} />
              {/* Follow-up emails hidden — backend SMTP endpoint not reachable.
                  Re-enable once /api/email/smtp-status is live or SMTP env is
                  configured in backend/.env, then restore the line below. */}
              {/* <FollowUpEmails summary={summary} /> */}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

// ── Page header — matches the active view ─────────────────
const HEADERS = {
  'audio':        ['Upload Audio',       'Upload a WAV, MP3, or M4A recording. Whisper will transcribe it and identify speakers.'],
  'realtime':     ['Real-Time Audio',    'Record directly from your microphone.'],
  'paste':        ['Paste Transcript',    'Paste an existing transcript to summarise.'],
  'text':         ['Upload Transcript',   'Upload a .txt transcript to summarise.'],
  'audio-player': ['Audio',              'The original recording — play, seek, and download.'],
  'transcript':   ['Transcript & Playback', 'Review the transcript, then generate a summary when you\'re ready.'],
  'confidence':   ['Confidence Scores',  'See where Whisper is confident and where the transcript may need review.'],
  'report':       ['Final Report',       'Meeting summary, action items, and speaker breakdown.'],
};

function ViewHeader({ activeView, hasResults, onReturnToResults }) {
  const [title, subtitle] = HEADERS[activeView] || ['', ''];
  const showReturn = hasResults && INPUT_VIEWS.has(activeView);
  return (
    <div className="app-view-header" style={{
      marginBottom: 22, display: 'flex', alignItems: 'flex-start',
      justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h1 style={{
          fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 30,
          letterSpacing: '-0.02em', margin: 0, color: '#0f172a',
        }}>{title}</h1>
        {subtitle && (
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 14.5 }}>{subtitle}</p>
        )}
      </div>
      {showReturn && (
        <button
          onClick={onReturnToResults}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(13,148,136,0.10)', color: '#0f766e',
            border: '1px solid rgba(13,148,136,0.35)', borderRadius: 999,
            padding: '7px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          You have results — view →
        </button>
      )}
    </div>
  );
}

const primaryBtn = {
  background: '#0d9488', color: '#0f172a', border: 'none', borderRadius: 11,
  padding: '10px 18px', fontSize: 14, fontWeight: 700, cursor: 'pointer',
};

const errorBox = {
  padding: '12px 14px', background: '#fef2f2',
  border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 10, fontSize: 13.5,
};
