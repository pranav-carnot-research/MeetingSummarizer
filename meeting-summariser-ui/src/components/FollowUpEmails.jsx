import React, { useEffect, useMemo, useState } from 'react';
import { Card, SectionTitle, Label, Button, Badge } from './Card.jsx';
import {
  smtpStatus, draftEmails, sendEmail, sendAllEmails,
  prefillContacts, saveContacts,
} from '../api/client.js';

// Group action items by assignee (mirrors follow_up_agent.group_by_assignee)
function groupByAssignee(items) {
  const groups = {};
  for (const it of items || []) {
    const a = (it.assignee || '').trim();
    if (!a || /^unassigned$/i.test(a)) continue;
    if (!groups[a]) groups[a] = [];
    groups[a].push(it);
  }
  return groups;
}

export default function FollowUpEmails({ summary }) {
  const [smtp, setSmtp] = useState({ configured: false, reason: 'Checking…' });
  const [senderName, setSenderName] = useState('Meeting Organiser');
  const [roster, setRoster] = useState({});
  const [drafts, setDrafts] = useState({});
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(null); // assignee name or 'all'
  const [results, setResults] = useState({});
  const [error, setError] = useState(null);

  const actionItems = summary?.action_items || [];
  const meetingSummary = summary?.meeting_summary || {};
  const groups = useMemo(() => groupByAssignee(actionItems), [actionItems]);
  const assignees = Object.keys(groups);

  useEffect(() => { smtpStatus().then(setSmtp); }, []);

  useEffect(() => {
    if (!assignees.length) return;
    prefillContacts(assignees).then((res) => {
      setRoster((prev) => ({ ...(res.roster || {}), ...prev }));
    });
  }, [assignees.length]);

  if (!assignees.length) return null;

  const doDraft = async () => {
    setDrafting(true);
    setError(null);
    try {
      const res = await draftEmails({ actionItems, meetingSummary, senderName });
      setDrafts(res.drafts || {});
      setResults({});
    } catch (e) {
      setError(e.message || 'Draft generation failed');
    } finally {
      setDrafting(false);
    }
  };

  const doSend = async (assignee) => {
    const to = roster[assignee];
    if (!to) return;
    setSending(assignee);
    try {
      const res = await sendEmail({ toAddress: to, body: drafts[assignee] });
      setResults((r) => ({ ...r, [assignee]: res }));
      if (res.success) saveContacts({ [assignee]: to });
    } catch (e) {
      setResults((r) => ({ ...r, [assignee]: { success: false, message: e.message } }));
    } finally {
      setSending(null);
    }
  };

  const doSendAll = async () => {
    setSending('all');
    try {
      const res = await sendAllEmails({ roster, drafts });
      const out = {};
      Object.entries(res.results || {}).forEach(([name, r]) => { out[name] = r; });
      setResults(out);
      const toSave = {};
      Object.entries(out).forEach(([name, r]) => {
        if (r.success && roster[name]) toSave[name] = roster[name];
      });
      if (Object.keys(toSave).length) saveContacts(toSave);
    } catch (e) {
      setError(e.message || 'Send-all failed');
    } finally {
      setSending(null);
    }
  };

  const allHaveEmails = assignees.every((a) => roster[a] && roster[a].includes('@'));

  return (
    <Card style={{ marginTop: 20 }}>
      <SectionTitle subtitle="One personalised email per assignee — listing their specific action items with meeting context. Preview and edit before sending.">
        📧 Send Follow-up Emails
      </SectionTitle>

      {/* SMTP banner */}
      {!smtp.configured && (
        <div style={{
          padding: '12px 14px', background: '#fef3c7', border: '1px solid #fcd34d',
          borderRadius: 10, color: '#92400e', fontSize: 13.5, marginBottom: 16,
        }}>
          ⚠️ SMTP not configured: {smtp.reason}. Fill in <code>SMTP_USER</code>, <code>SMTP_PASSWORD</code> (and optionally <code>SMTP_HOST</code>) in your <code>.env</code>, then restart the backend.
        </div>
      )}

      {/* Step 1: Roster */}
      <div style={{ marginBottom: 20 }}>
        <div style={stepHead}>Step 1 — Enter email addresses</div>
        <div style={stepHint}>Known contacts are auto-filled. Changes are remembered for future meetings.</div>
        {assignees.map((a) => (
          <div key={a} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12, alignItems: 'center', marginTop: 8 }}>
            <div style={{ fontSize: 14 }}>
              <strong>{a}</strong> <span style={{ color: '#94a3b8', fontSize: 12.5 }}>· {groups[a].length} task{groups[a].length > 1 ? 's' : ''}</span>
            </div>
            <input
              value={roster[a] || ''}
              onChange={(e) => setRoster((r) => ({ ...r, [a]: e.target.value }))}
              placeholder="name@company.com"
              style={inputStyle}
            />
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div>
          <Label>Your name (sender)</Label>
          <input value={senderName} onChange={(e) => setSenderName(e.target.value)} style={inputStyle} />
        </div>
      </div>

      {/* Step 2: Drafts */}
      <div style={{ marginBottom: 20 }}>
        <div style={stepHead}>Step 2 — Generate drafts</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
          <Button onClick={doDraft} disabled={drafting} variant="teal">
            {drafting ? 'Drafting…' : '✍️ Generate Email Drafts'}
          </Button>
          {Object.keys(drafts).length > 0 && (
            <Button variant="ghost" onClick={() => { setDrafts({}); setResults({}); }}>
              🗑 Clear Drafts
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca',
          color: '#b91c1c', borderRadius: 10, fontSize: 13.5, marginBottom: 16,
        }}>{error}</div>
      )}

      {/* Step 3: Preview + send */}
      {Object.keys(drafts).length > 0 && (
        <div>
          <div style={stepHead}>Step 3 — Preview, edit, send</div>
          {Object.entries(drafts).map(([assignee, body]) => {
            const r = results[assignee];
            const badge = r ? (r.success ? '✅ Sent' : '❌ Failed') : '📝 Draft';
            const badgeColor = r ? (r.success ? '#10b981' : '#ef4444') : '#0d9488';
            return (
              <details key={assignee} open={!r} style={{
                border: '1px solid #e2e8f0', borderRadius: 12, marginTop: 10, background: '#fff',
              }}>
                <summary style={{
                  padding: '12px 14px', cursor: 'pointer', display: 'flex',
                  alignItems: 'center', gap: 10, fontSize: 14,
                }}>
                  <Badge color={badgeColor}>{badge}</Badge>
                  <strong>{assignee}</strong>
                  <span style={{ color: '#94a3b8', fontSize: 12.5 }}>· {groups[assignee].length} task{groups[assignee].length > 1 ? 's' : ''}</span>
                  <span style={{ marginLeft: 'auto', color: '#94a3b8', fontSize: 12.5 }}>
                    {roster[assignee] || 'no email'}
                  </span>
                </summary>
                <div style={{ padding: '10px 14px 14px' }}>
                  <textarea
                    value={body}
                    onChange={(e) => setDrafts((d) => ({ ...d, [assignee]: e.target.value }))}
                    style={{
                      width: '100%', minHeight: 220, padding: 12, borderRadius: 10,
                      border: '1px solid #cbd5e1', fontSize: 13.5, fontFamily: "'Inter', sans-serif",
                      lineHeight: 1.5, resize: 'vertical', boxSizing: 'border-box',
                    }}
                  />
                  <div style={{ marginTop: 10, display: 'flex', gap: 10 }}>
                    <Button
                      onClick={() => doSend(assignee)}
                      disabled={
                        !smtp.configured || !roster[assignee] || !roster[assignee].includes('@') ||
                        sending === assignee
                      }
                    >
                      {sending === assignee ? 'Sending…' : `📤 Send to ${roster[assignee] || 'N/A'}`}
                    </Button>
                    {r && !r.success && (
                      <div style={{ color: '#b91c1c', fontSize: 13, alignSelf: 'center' }}>{r.message}</div>
                    )}
                  </div>
                </div>
              </details>
            );
          })}

          <div style={{ marginTop: 18 }}>
            <Button
              variant="teal"
              onClick={doSendAll}
              disabled={!smtp.configured || !allHaveEmails || sending !== null}
            >
              {sending === 'all' ? 'Sending all…' : '📤 Send All Emails'}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

const stepHead = { fontFamily: "'Manrope', sans-serif", fontWeight: 700, fontSize: 15, color: '#0f172a' };
const stepHint = { color: '#64748b', fontSize: 13, marginTop: 2 };
const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14, color: '#111',
  outline: 'none', boxSizing: 'border-box',
};
