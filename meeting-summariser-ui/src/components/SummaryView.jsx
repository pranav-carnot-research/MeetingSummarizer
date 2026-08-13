import React, { useState } from 'react';
import { Download, FileJson, FileText, ChevronDown, ChevronRight, CheckCircle2, HelpCircle } from 'lucide-react';
import { Card, Button, Badge } from './Card.jsx';

const priorityColor = (p) => {
  const key = (p || 'medium').toLowerCase();
  if (key === 'high') return '#ef4444';
  if (key === 'low') return '#10b981';
  return '#f59e0b';
};

// Turn a wall-of-text summary into readable paragraphs. Prefers explicit
// paragraph breaks (`\n\n`) from the LLM if present; otherwise groups the
// prose into ~2-sentence paragraphs so each block is scannable instead of
// a single ~500-word slab.
function splitSummaryParagraphs(text) {
  if (!text) return [];
  const byBlanks = text.split(/\n{2,}/).map((s) => s.trim()).filter(Boolean);
  if (byBlanks.length > 1) return byBlanks;
  const sentences = text.match(/[^.!?]+[.!?]+(?:["')\]]+)?\s*/g);
  if (!sentences || sentences.length <= 2) return [text.trim()];
  const SIZE = 2;
  const chunks = [];
  for (let i = 0; i < sentences.length; i += SIZE) {
    chunks.push(sentences.slice(i, i + SIZE).join('').trim());
  }
  return chunks;
}

function downloadBlob(filename, content, mime = 'text/plain') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function SummaryView({ summary, transcript }) {
  const [tab, setTab] = useState('summary');
  const [expandedAction, setExpandedAction] = useState(null);
  const [expandedSpeaker, setExpandedSpeaker] = useState(null);

  if (!summary) return null;

  const meetingSummary = summary.meeting_summary || (summary.summary ? summary : {});
  const rawSummaryText = meetingSummary.summary || summary.summary || (typeof summary === 'string' ? summary : '');
  const actionItems = summary.action_items || meetingSummary.action_items || [];
  const speakerSummaries = summary.speaker_summaries || meetingSummary.speaker_summaries || {};
  const metadata = summary.metadata || meetingSummary.metadata || {};

  const exportExecutivePDF = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    const keyPointsHtml = (meetingSummary.key_points || [])
      .map(kp => `<li style="margin-bottom: 8px; line-height: 1.6; color: #334155;">${kp}</li>`)
      .join('');

    const decisionsHtml = (meetingSummary.decisions || [])
      .map(d => `<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #16a34a; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; font-size: 13.5px; color: #166534; font-weight: 600;">✓ ${d}</div>`)
      .join('');

    const actionItemsHtml = actionItems.map(item => {
      const prio = (item.priority || 'medium').toLowerCase();
      const prioBg = prio === 'high' ? '#fee2e2' : prio === 'low' ? '#d1fae5' : '#fef3c7';
      const prioColor = prio === 'high' ? '#991b1b' : prio === 'low' ? '#065f46' : '#92400e';
      return `
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 10px 12px; font-weight: 600; color: #0f172a;">${item.action || 'Untitled Action'}</td>
          <td style="padding: 10px 12px; color: #334155;">${item.assignee || 'Unassigned'}</td>
          <td style="padding: 10px 12px;"><span style="background: ${prioBg}; color: ${prioColor}; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px; text-transform: uppercase;">${prio}</span></td>
          <td style="padding: 10px 12px; color: #64748b; font-size: 12.5px;">${item.due_date || 'Not specified'}</td>
        </tr>
      `;
    }).join('');

    const html = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Executive Meeting Minutes - Carnot Research</title>
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Manrope:wght@700;800&display=swap');
          @page { size: A4; margin: 15mm; }
          body { font-family: 'Inter', -apple-system, sans-serif; color: #0f172a; margin: 0; padding: 24px; }
          .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #0d9488; padding-bottom: 16px; margin-bottom: 20px; }
          .logo-box { display: flex; align-items: center; gap: 12px; }
          .logo-img { height: 38px; width: auto; }
          .title-box { text-align: right; }
          .doc-title { font-family: 'Manrope', sans-serif; font-size: 20px; font-weight: 800; color: #0f172a; margin: 0; text-transform: uppercase; letter-spacing: -0.01em; }
          .doc-sub { font-size: 12px; color: #0d9488; font-weight: 600; margin-top: 2px; }
          .meta-bar { display: flex; gap: 24px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 18px; margin-bottom: 24px; font-size: 13px; color: #475569; }
          .meta-item strong { color: #0f172a; }
          .section-head { font-family: 'Manrope', sans-serif; font-size: 14px; font-weight: 800; color: #0f172a; text-transform: uppercase; letter-spacing: 0.05em; border-left: 4px solid #0d9488; padding-left: 10px; margin: 24px 0 12px 0; }
          .summary-box { background: #fafbfc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488; border-radius: 6px; padding: 16px; font-size: 14px; color: #334155; line-height: 1.6; }
          table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
          th { background: #0f172a; color: #ffffff; text-align: left; padding: 10px 12px; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.04em; }
          .footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="logo-box">
            <img src="/icarkno%20logo.png" class="logo-img" alt="Carnot Research Logo" />
          </div>
          <div class="title-box">
            <h1 class="doc-title">Executive Meeting Minutes</h1>
            <div class="doc-sub">Carnot Research · Meeting Intelligence</div>
          </div>
        </div>

        <div class="meta-bar">
          <div class="meta-item"><strong>Date:</strong> ${new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</div>
          <div class="meta-item"><strong>Language:</strong> ${metadata.language_name || metadata.language || 'English'}</div>
          <div class="meta-item"><strong>Action Items:</strong> ${actionItems.length}</div>
          <div class="meta-item"><strong>Decisions:</strong> ${(meetingSummary.decisions || []).length}</div>
        </div>

        <div class="section-head">1. Executive Summary</div>
        <div class="summary-box">${meetingSummary.summary || 'No summary available.'}</div>

        ${(meetingSummary.key_points || []).length > 0 ? `
          <div class="section-head">2. Key Discussion Points</div>
          <ul style="margin: 0; padding-left: 20px; font-size: 13.5px; color: #334155;">
            ${keyPointsHtml}
          </ul>
        ` : ''}

        ${(meetingSummary.decisions || []).length > 0 ? `
          <div class="section-head">3. Decisions Made</div>
          ${decisionsHtml}
        ` : ''}

        ${actionItems.length > 0 ? `
          <div class="section-head">4. Action Items & Assignments</div>
          <table>
            <thead>
              <tr>
                <th>Action Item</th>
                <th>Assignee</th>
                <th>Priority</th>
                <th>Due Date</th>
              </tr>
            </thead>
            <tbody>
              ${actionItemsHtml}
            </tbody>
          </table>
        ` : ''}

        <div class="footer">
          <div>Carnot Research Meeting Intelligence System</div>
          <div>Confidential · Executive Report</div>
        </div>

        <script>
          window.onload = function() {
            setTimeout(function() {
              window.print();
            }, 400);
          };
        </script>
      </body>
      </html>
    `;

    printWindow.document.write(html);
    printWindow.document.close();
  };

  const buildCleanTextReport = () => {
    const lines = [];
    lines.push('MEETING MINUTES REPORT - CARNOT RESEARCH');
    lines.push(`Date: ${new Date().toLocaleDateString()}`);
    lines.push(`Language: ${metadata.language_name || metadata.language || 'English'}\n`);
    lines.push('1. EXECUTIVE SUMMARY\n' + (meetingSummary.summary || 'No summary available.') + '\n');
    lines.push('2. KEY POINTS');
    (meetingSummary.key_points || []).forEach((k) => lines.push(`• ${k}`));
    lines.push('\n3. DECISIONS MADE');
    (meetingSummary.decisions || []).forEach((d) => lines.push(`✓ ${d}`));
    lines.push('\n4. ACTION ITEMS');
    actionItems.forEach((it) => {
      lines.push(`📌 ${it.action || ''}`);
      lines.push(`   Assignee: ${it.assignee || 'Unassigned'} | Due: ${it.due_date || 'Not specified'} | Priority: ${(it.priority || 'medium').toUpperCase()}`);
    });
    return lines.join('\n');
  };

  // Downloads render in two slots (desktop top-right; mobile bottom) —
  // CSS toggles which one is visible per viewport. Kept as one JSX
  // fragment so the button set stays a single source of truth.
  const downloadButtons = (
    <>
      <Button variant="ghost" onClick={() => downloadBlob('meeting_summary.json', JSON.stringify(summary, null, 2), 'application/json')}>
        <FileJson size={14} style={{ display: 'inline-block', marginRight: 6 }} />
        JSON
      </Button>
      <Button variant="ghost" onClick={() => downloadBlob('transcript.txt', transcript || '', 'text/plain')} disabled={!transcript}>
        <FileText size={14} style={{ display: 'inline-block', marginRight: 6 }} />
        Transcript
      </Button>
      <Button variant="ghost" onClick={() => downloadBlob('meeting_report.txt', buildFullReport(), 'text/plain')}>
        <Download size={14} style={{ display: 'inline-block', marginRight: 6 }} />
        Full report
      </Button>
      <Button
        style={{
          background: 'linear-gradient(135deg, #0d9488, #0f766e)',
          color: '#ffffff',
          fontWeight: 600,
          border: 'none',
          padding: '8px 16px',
          borderRadius: 8,
          cursor: 'pointer',
          boxShadow: '0 2px 4px rgba(13,148,136,0.2)',
        }}
        onClick={exportExecutivePDF}
      >
        <Download size={14} style={{ display: 'inline-block', marginRight: 6 }} />
        Executive PDF Report
      </Button>
    </>
  );

  return (
    <Card>
      {/* Tabs (always shown) + downloads (desktop-only here). On mobile the
          downloads move to a dedicated block at the bottom of the card —
          see .app-downloads-bottom below. */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, flexWrap: 'wrap', marginBottom: 20,
      }}>
        <div style={{
          display: 'flex', gap: 6, background: '#f1f5f9',
          padding: 5, borderRadius: 12,
        }}>
          {[
            { id: 'summary', label: 'Meeting Summary' },
            { id: 'speakers', label: 'Speaker Summaries' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: '8px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
                fontSize: 14, fontWeight: 600,
                background: tab === t.id ? '#fff' : 'transparent',
                color: tab === t.id ? COLOR.text : COLOR.muted,
                boxShadow: tab === t.id ? '0 1px 4px rgba(17,17,17,0.08)' : 'none',
              }}
            >{t.label}</button>
          ))}
        </div>

        <div className="app-downloads-top" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {downloadButtons}
        </div>
      </div>

      {tab === 'summary' && (() => {
        const summaryParagraphs = splitSummaryParagraphs(rawSummaryText);
        return (
        <div>
          {/* Summary Section (First) */}
          <div style={{ marginBottom: 28 }}>
            <div style={sectionHeadStyle}>Summary</div>
            {summaryParagraphs.length === 0 ? (
              <em style={{ color: COLOR.subtle, fontSize: 14 }}>No summary available.</em>
            ) : (
              summaryParagraphs.map((para, idx) => (
                <p key={idx} style={{ ...bodyStyle, marginTop: idx === 0 ? 0 : 14 }}>{para}</p>
              ))
            )}
          </div>

          <div className="app-summary-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <div>
              <SectionList
                title="Key Points"
                accent="#0d9488"
                items={meetingSummary.key_points || []}
                marker="dot"
                emptyLabel="No key points captured."
              />

              <SectionList
                title="Decisions"
                accent="#0d9488"
                items={meetingSummary.decisions || []}
                marker="check"
                emptyLabel="No decisions were recorded."
              />
            </div>

            <div>
              <div style={sectionHeadStyle}>Action Items ({actionItems.length})</div>
              {actionItems.length === 0 && <div style={emptyStyle}>No action items identified.</div>}
              {actionItems.map((item, i) => {
              const open = expandedAction === i;
              return (
                <div key={i} style={{
                  border: `1px solid ${COLOR.border}`, borderRadius: 12, marginBottom: 10, background: '#fff',
                }}>
                  <button
                    onClick={() => setExpandedAction(open ? null : i)}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 14px', background: 'transparent', border: 'none', cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600, color: COLOR.text, fontSize: 14 }}>
                      {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      {item.action || 'Untitled action'}
                    </span>
                    <Badge color={priorityColor(item.priority)}>{(item.priority || 'medium').toUpperCase()}</Badge>
                  </button>
                  {open && (
                    <div style={{ padding: '4px 14px 14px 40px', ...metaStyle }}>
                      <div><strong>Assignee:</strong> {item.assignee || 'Unassigned'}</div>
                      <div><strong>Due date:</strong> {item.due_date || 'Not specified'}</div>
                      {item.notes && <div style={{ marginTop: 4 }}><strong>Notes:</strong> {item.notes}</div>}
                    </div>
                  )}
                </div>
              );
            })}
            </div>
          </div>

          {metadata && Object.keys(metadata).length > 0 && (
            <div style={{
              marginTop: 24, padding: 14, borderRadius: 10, background: COLOR.surface,
              border: `1px solid ${COLOR.border}`, ...metaStyle,
            }}>
              <div><strong>Language:</strong> {metadata.language_name || metadata.language || 'Unknown'}</div>
              <div><strong>Participants:</strong> {metadata.participant_count ?? '—'}</div>
              {metadata.is_long_recording !== undefined && (
                <div><strong>Long recording:</strong> {metadata.is_long_recording ? 'Yes' : 'No'}</div>
              )}
            </div>
          )}
        </div>
        );
      })()}

      {tab === 'speakers' && (
        <div>
          {Object.keys(speakerSummaries).length === 0 && (
            <div style={emptyStyle}>No speaker summaries available.</div>
          )}
          {Object.entries(speakerSummaries).map(([speaker, s], i) => {
            const open = expandedSpeaker === i;
            return (
              <div key={speaker} style={{
                border: `1px solid ${COLOR.border}`, borderRadius: 12, marginBottom: 10, background: '#fff',
              }}>
                <button
                  onClick={() => setExpandedSpeaker(open ? null : i)}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                    padding: '14px 16px', background: 'transparent', border: 'none', cursor: 'pointer',
                    textAlign: 'left', fontSize: 15, fontWeight: 700, color: COLOR.text,
                    fontFamily: FONT_HEADING, letterSpacing: '-0.01em',
                  }}
                >
                  {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  {speaker}
                </button>
                {open && (
                  <div style={{ padding: '4px 20px 18px 42px', fontSize: 14, color: COLOR.text }}>
                    <div style={{ marginBottom: 10 }}>{s.brief_summary || <em style={{ color: COLOR.subtle }}>No summary.</em>}</div>
                    {s.key_contributions?.length > 0 && (
                      <SectionList
                        title="Key contributions"
                        accent="#0d9488"
                        items={s.key_contributions}
                        marker="dot"
                      />
                    )}
                    {s.action_items?.length > 0 && (
                      <SectionList
                        title="Action items"
                        accent="#0d9488"
                        items={s.action_items}
                        marker="check"
                      />
                    )}
                    {s.questions_raised?.length > 0 && (
                      <SectionList
                        title="Questions raised"
                        accent="#0d9488"
                        items={s.questions_raised}
                        marker="question"
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Mobile-only download bar. On desktop the buttons live in the top
          row next to the tabs (.app-downloads-top); on mobile they move
          here so the top row stays free for the tab switcher alone. */}
      <div
        className="app-downloads-bottom"
        style={{
          display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center',
          marginTop: 28, paddingTop: 20, borderTop: `1px solid ${COLOR.border}`,
        }}
      >
        {downloadButtons}
      </div>
    </Card>
  );
}

// Minimal list section — clean typography, subtle marker per item.
// The marker shape (dot / check / question) is the only differentiator
// between list *kinds* (topics discussed vs resolved decisions vs open
// questions). Everything else — heading style, item color, spacing —
// comes from the shared tokens above.
function SectionList({ title, accent = COLOR.accent, items, marker, emptyLabel }) {
  return (
    <div>
      <div style={sectionHeadStyle}>{title}</div>

      {items.length === 0 && <div style={emptyStyle}>{emptyLabel}</div>}

      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
        {items.map((item, i) => (
          <li key={i} style={{
            display: 'flex', gap: 12, alignItems: 'flex-start',
            padding: '6px 0', fontSize: 14, lineHeight: 1.6, color: COLOR.text,
          }}>
            {marker === 'check' ? (
              <CheckCircle2
                size={15}
                color={accent}
                strokeWidth={2.25}
                style={{ flexShrink: 0, marginTop: 3 }}
              />
            ) : marker === 'question' ? (
              <HelpCircle
                size={15}
                color={accent}
                strokeWidth={2.25}
                style={{ flexShrink: 0, marginTop: 3 }}
              />
            ) : (
              <span style={{
                flexShrink: 0, marginTop: 9, width: 5, height: 5,
                borderRadius: '50%', background: accent,
              }} />
            )}
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Design tokens — one source of truth for SummaryView ─────────────
// Before: three different "dark" body colours (#333/#111/#0f172a) and
// two different heading systems (15px dark vs 12px muted eyebrow) were
// scattered across the file. Everything below routes through these
// tokens so section headers, body text, and metadata are visually
// coherent across the Meeting Summary and Speakers tabs.
const COLOR = {
  text:    '#0f172a',   // primary body + high-contrast labels
  muted:   '#64748b',   // secondary body + metadata
  subtle:  '#94a3b8',   // tertiary (eyebrow labels, empty states)
  accent:  '#0d9488',   // teal — markers + active states
  border:  '#e2e8f0',
  surface: '#f8fafc',
};
const FONT_HEADING = "'Manrope', sans-serif";

// One heading style for every section header in the view. Small uppercase
// eyebrow keeps content as the visual focus; headers scaffold it.
const sectionHeadStyle = {
  fontFamily: FONT_HEADING,
  fontWeight: 700,
  fontSize: 12,
  letterSpacing: '.1em',
  textTransform: 'uppercase',
  color: COLOR.subtle,
  margin: '24px 0 12px',
};
const bodyStyle = {
  color: COLOR.text,
  fontSize: 14.5,
  lineHeight: 1.65,
  margin: 0,
};
const metaStyle = {
  color: COLOR.muted,
  fontSize: 13,
  lineHeight: 1.6,
};
const emptyStyle = {
  color: COLOR.subtle,
  fontStyle: 'italic',
  fontSize: 13.5,
};
