import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

// ─── Word-by-word reveal (ported from profile-website hero) ───────────────────
// Tuned for landing-page speed: CTA needs to appear in <1.5s.
const CHAR_STAGGER = 0.010;
const LETTER_REVEAL_DURATION = 0.45;

function Words({ text, color, delay = 0, style }) {
  const letters = Array.from(text);
  const segments = [];
  let i = 0;
  while (i < letters.length) {
    const start = i;
    const isSpace = letters[i] === ' ';
    while (i < letters.length && (letters[i] === ' ') === isSpace) i++;
    segments.push({ word: letters.slice(start, i).join(''), startIdx: start });
  }
  return (
    <>
      {segments.map((seg, si) => {
        const isSpaceSeg = seg.word[0] === ' ';
        return (
          <span
            key={si}
            style={isSpaceSeg ? undefined : { display: 'inline-block', whiteSpace: 'nowrap', ...style }}
          >
            {Array.from(seg.word).map((char, ci) => (
              <span
                key={ci}
                style={{
                  display: 'inline-block',
                  color,
                  opacity: 0,
                  animation: 'wordReveal 0.55s cubic-bezier(0.22,1,0.36,1) both',
                  animationDelay: `${delay + (seg.startIdx + ci) * CHAR_STAGGER}s`,
                }}
              >
                {char === ' ' ? ' ' : char}
              </span>
            ))}
          </span>
        );
      })}
    </>
  );
}

const features = [
  { glyph: '🔒', title: 'On-premise & secure', desc: 'Runs entirely inside your VPC or data center. Nothing is sent to external servers, ever.' },
  { glyph: '≡', title: 'Four ways in', desc: 'Upload audio, record live, paste raw text, or import a transcript file — whatever fits the moment.' },
  { glyph: '◎', title: 'Speakers detected', desc: 'Participants are identified automatically from the conversation. No manual tagging.' },
  { glyph: '✓', title: 'Action items with owners', desc: 'Every task is extracted with its owner and deadline, ready to paste into your tracker.' },
  { glyph: '◇', title: 'Multi-language', desc: 'Auto-detects the spoken language, or set it manually for maximum accuracy.' },
  { glyph: '⏱', title: 'Long-meeting mode', desc: 'Optimized processing for sessions over 15 minutes without losing detail.' },
];

const steps = [
  { n: '1', title: 'Choose your input', desc: 'Upload audio, record live, paste text, or import a transcript file.' },
  { n: '2', title: 'AI transcribes', desc: 'Speech becomes text and the conversation is parsed for structure and intent.' },
  { n: '3', title: 'Speakers identified', desc: 'Participants and topics are detected automatically from the transcript.' },
  { n: '4', title: 'Summary delivered', desc: 'A concise summary with action items, owners, and deadlines.' },
];

const securityPoints = [
  'Deployed entirely within your own VPC or data center',
  'No third-party AI APIs or external data retention',
  'Full audit trail for every processed meeting',
];

const marqueeItems = [
  'NO THIRD-PARTY APIS', 'ON-PREMISE', 'SPEAKER DETECTION', 'ACTION ITEMS',
  'MULTI-LANGUAGE', 'REAL-TIME', 'NO THIRD-PARTY APIS', 'ON-PREMISE',
  'SPEAKER DETECTION', 'ACTION ITEMS', 'MULTI-LANGUAGE', 'REAL-TIME',
];

// ─────────────────────────────────────────────────────────────
// "How it works" — typographic horizontal flow. No images, no mockups.
// The step number IS the visual: giant outlined numerals, each connected
// by a thin flowing arrow. Minimal, editorial, on-brand.
// ─────────────────────────────────────────────────────────────

function HowItWorks({ steps, reveal, stagger }) {
  return (
    <section id="how" style={{ maxWidth: 1180, margin: '0 auto', padding: '0 24px' }}>
      <style>{`
        .how-num {
          font-family: 'Manrope', sans-serif;
          font-weight: 800;
          font-size: clamp(96px, 11vw, 160px);
          line-height: .82;
          letter-spacing: -0.06em;
          color: transparent;
          -webkit-text-stroke: 1.5px #0f172a;
          transition: -webkit-text-stroke .35s ease, color .35s ease, transform .35s ease;
        }
        .how-step:hover .how-num {
          color: #0d9488;
          -webkit-text-stroke: 1.5px #0d9488;
          transform: translateY(-4px);
        }
        .how-arrow { color: #0f172a; opacity: .55; transition: opacity .35s ease, color .35s ease, transform .35s ease; }
        .how-step:hover ~ .how-arrow,
        .how-arrow.is-active { color: #0d9488; opacity: 1; transform: translateX(4px); }
      `}</style>

      <div {...reveal('how-header', { textAlign: 'center', marginBottom: 72 })} className="lp-how-heading">
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.1em', color: '#94a3b8', marginBottom: 12 }}>HOW IT WORKS</div>
        <h2 style={{ fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 42, letterSpacing: '-0.02em', margin: 0, color: '#0f172a' }}>
          From recording to action items
        </h2>
        <p style={{ fontSize: 15.5, color: '#64748b', marginTop: 14 }}>Four stages. All local.</p>
      </div>

      {/* Two-row grid: row 1 = numbers + arrows (arrows centered on the
          number's mid-line), row 2 = title + description under each number.
          On mobile the CSS media query collapses this to a single column,
          hides the arrows, and lets step blocks stack in source order. */}
      <div className="lp-how-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0,1fr) 64px minmax(0,1fr) 64px minmax(0,1fr) 64px minmax(0,1fr)',
        gridTemplateRows: 'auto auto',
        alignItems: 'start',
        columnGap: 0,
        rowGap: 4,
      }}>
        {steps.map((s, i) => (
          <React.Fragment key={i}>
            {/* Row 1: giant centered number */}
            <div
              {...stagger(`step-${i}`, i)}
              className="how-step lp-how-step"
              style={{
                gridColumn: (i * 2) + 1,
                gridRow: 1,
                textAlign: 'center',
                display: 'flex', justifyContent: 'center', alignItems: 'center',
              }}
            >
              <div className="how-num">{s.n}</div>
            </div>

            {/* Row 1: arrow between steps, vertically centered on the number */}
            {i < steps.length - 1 && (
              <div className="how-arrow lp-how-arrow" style={{
                gridColumn: (i * 2) + 2,
                gridRow: 1,
                alignSelf: 'center',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'color .35s ease',
              }}>
                <FlowArrow />
              </div>
            )}

            {/* Row 2: title + description centered under the number */}
            <div className="lp-how-title-block" style={{
              gridColumn: (i * 2) + 1,
              gridRow: 2,
              textAlign: 'center',
              padding: '0 10px',
            }}>
              <div style={{ height: 1, background: '#e2e8f0', margin: '22px auto 20px', maxWidth: 96 }} />
              <h3 style={{
                fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 22,
                margin: 0, color: '#0f172a', letterSpacing: '-0.01em', lineHeight: 1.15,
              }}>{s.title}</h3>
              <p style={{
                margin: '10px 0 0', fontSize: 14.5, lineHeight: 1.6, color: '#64748b',
              }}>{s.desc}</p>
            </div>
          </React.Fragment>
        ))}
      </div>
    </section>
  );
}

function FlowArrow() {
  // Solid shaft + filled triangular head. Reads as clear directional flow
  // from one step to the next. Uses currentColor so hover states can tint it.
  return (
    <svg width="56" height="18" viewBox="0 0 56 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M2 9 H44" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M42 2 L54 9 L42 16 Z" fill="currentColor" />
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────
// Sticky "why teams use it" section:
//   - The heading pins at top of viewport while the section is on screen.
//   - Cards below it also use position:sticky, each with the SAME top
//     (equal to header height + a little space), so cards stack ON TOP of
//     each other under the pinned header as you scroll.
//   - We track which card is fully "locked" to update a small
//     "01/06" progress badge inside the header.
// IMPORTANT: no ancestor may set `overflow` (other than visible) or a
// `transform` — either breaks position:sticky.
// ─────────────────────────────────────────────────────────────
// Layout tokens for the sticky Features section.
// The navbar is now flush to top: 0 with ~78px total height (12px pad + pill),
// so the pinned Features heading starts just below it.
// The navbar sits at top:0 with ~78px total height. Cards lock a short
// distance below it. (The section heading is no longer sticky, so
// NAVBAR_BOTTOM and HEADER_HEIGHT are just used to derive CARD_TOP.)
// Sticky nav pill measures ~78px (12px top-pad + 66px pill) at top:0.
// Give the pinned Features heading a small gap below the nav.
const NAVBAR_BOTTOM = 90;
const HEADER_HEIGHT = 112;
const CARD_TOP      = NAVBAR_BOTTOM + HEADER_HEIGHT + 24;
const CARD_MIN_H    = 380;

function FeaturesSection({ features }) {
  // JS-controlled sticky heading.
  // Sticky-CSS can't align the heading and cards' unpin points (they have
  // different `top` values, so they unpin at different scroll positions).
  // Instead: track the section's bounding rect on scroll and toggle sticky
  // OFF the instant the last card would unpin. Heading + cards then scroll
  // out of the section together — no overlap possible.
  const sectionRef = useRef(null);
  const [headingPinned, setHeadingPinned] = useState(false);
  const unpinThreshold = CARD_TOP + CARD_MIN_H; // matches when cards unpin

  useEffect(() => {
    const check = () => {
      const el = sectionRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      // Pin only while:
      //   - the section has been scrolled up to the pinning line, AND
      //   - the section's bottom is still below the cards' unpin threshold
      //     (so the last card is still stacking; heading belongs above it)
      setHeadingPinned(rect.top <= NAVBAR_BOTTOM && rect.bottom > unpinThreshold);
    };
    check();
    window.addEventListener('scroll', check, { passive: true });
    window.addEventListener('resize', check);
    return () => {
      window.removeEventListener('scroll', check);
      window.removeEventListener('resize', check);
    };
  }, [unpinThreshold]);

  const palettes = [
    { bg: 'linear-gradient(150deg,#0f172a 0%,#1e293b 100%)', color: '#fff', accent: '#0d9488', muted: 'rgba(255,255,255,0.75)', chipBg: 'rgba(13,148,136,0.16)' },
    { bg: 'linear-gradient(150deg,#0d9488 0%,#0b7c72 100%)', color: '#f8fafc', accent: '#f8fafc', muted: 'rgba(255,255,255,0.85)', chipBg: 'rgba(255,255,255,0.14)' },
    { bg: 'linear-gradient(150deg,#ffffff 0%,#f1f5f9 100%)', color: '#0f172a', accent: '#0d9488', muted: '#64748b', chipBg: '#e2e8f0' },
    { bg: 'linear-gradient(150deg,#0f172a 0%,#334155 100%)', color: '#fff', accent: '#0d9488', muted: 'rgba(255,255,255,0.75)', chipBg: 'rgba(255,255,255,0.10)' },
    { bg: 'linear-gradient(150deg,#f1f5f9 0%,#e2e8f0 100%)', color: '#0f172a', accent: '#0d9488', muted: '#64748b', chipBg: 'rgba(13,148,136,0.10)' },
    { bg: 'linear-gradient(150deg,#0d9488 0%,#0f172a 100%)', color: '#fff', accent: '#fff', muted: 'rgba(255,255,255,0.78)', chipBg: 'rgba(255,255,255,0.14)' },
  ];

  return (
    <section
      ref={sectionRef}
      id="features"
      className="lp-features-section"
      style={{
        maxWidth: 1180, margin: '112px auto 112px', padding: '0 24px',
        position: 'relative',
      }}
    >
      <div className="lp-features-heading" style={{
        padding: '20px 0 22px',
        marginBottom: 16,
        minHeight: HEADER_HEIGHT,
        boxSizing: 'border-box',
        visibility: headingPinned ? 'hidden' : 'visible',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.1em', color: '#94a3b8', marginBottom: 10 }}>
            WHY TEAMS USE IT
          </div>
          <h2 style={{
            fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 42,
            letterSpacing: '-0.02em', margin: 0, color: '#0f172a',
          }}>Built for how teams actually meet</h2>
        </div>
      </div>
      {headingPinned && (
        <div className="lp-features-heading" style={{
          position: 'fixed', top: NAVBAR_BOTTOM, left: 0, right: 0, zIndex: 20,
          background: '#fafbfc',
          padding: '20px 0 22px',
          pointerEvents: 'none',
        }}>
          <div style={{ textAlign: 'center', maxWidth: 1180, margin: '0 auto', padding: '0 24px' }}>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.1em', color: '#94a3b8', marginBottom: 10 }}>
              WHY TEAMS USE IT
            </div>
            <h2 style={{
              fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 42,
              letterSpacing: '-0.02em', margin: 0, color: '#0f172a',
            }}>Built for how teams actually meet</h2>
          </div>
        </div>
      )}

      {/* STACKING CARDS.
          A trailing spacer with height ≥ CARD_MIN_H gives the LAST card
          the same sticky duration every other card has (each card pins
          while the *next* card's flow position scrolls up under it — the
          last card has no "next", so we simulate one with a spacer).
          Without this, the last card would flash and immediately slide out. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 34 }}>
        {features.map((f, i) => {
          const p = palettes[i % palettes.length];
          const isDark = p.color === '#fff';
          return (
            <div
              key={i}
              className="lp-feature-card"
              style={{
                position: 'sticky',
                top: CARD_TOP,      // every card locks at the same line
                background: p.bg,
                color: p.color,
                borderRadius: 24,
                padding: '38px 44px',
                minHeight: CARD_MIN_H,
                display: 'grid',
                gridTemplateColumns: '1fr 1.25fr',
                gap: 36,
                alignItems: 'center',
                overflow: 'hidden',
                boxSizing: 'border-box',
              }}
            >
              {/* Left column: index chip + big glyph tile */}
              <div>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  background: p.chipBg, color: p.accent,
                  padding: '5px 12px', borderRadius: 999,
                  fontSize: 11.5, fontWeight: 800, letterSpacing: '.12em',
                }}>{String(i + 1).padStart(2, '0')} · REASON</div>
                <div style={{
                  marginTop: 22, width: 76, height: 76, borderRadius: 20,
                  background: p.chipBg, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', fontSize: 34, color: p.accent,
                }}>{f.glyph}</div>
              </div>

              {/* Right column: headline + copy */}
              <div>
                <h3 style={{
                  fontFamily: "'Manrope',sans-serif", fontWeight: 800,
                  fontSize: 30, lineHeight: 1.1, letterSpacing: '-0.02em',
                  margin: '0 0 16px', color: p.color,
                  paddingBottom: 16,
                  borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.20)' : 'rgba(15,23,42,0.12)'}`,
                }}>{f.title}</h3>
                <p style={{
                  margin: 0, fontSize: 16, lineHeight: 1.6, fontWeight: 500,
                  color: p.muted, maxWidth: 520,
                }}>{f.desc}</p>
              </div>
            </div>
          );
        })}
        {/* Trailing spacer — gives the LAST card its full pinned reveal */}
        <div aria-hidden="true" style={{ height: CARD_MIN_H }} />
      </div>
    </section>
  );
}


export default function Landing() {
  const navigate = useNavigate();
  const [revealed, setRevealed] = useState({});
  const revealMap = useRef({});
  const [ctaHover, setCtaHover] = useState(false);
  const [bigCtaHover, setBigCtaHover] = useState(false);

  const register = (id) => (el) => {
    if (el) revealMap.current[id] = el;
  };

  useEffect(() => {
    const check = () => {
      const vh = window.innerHeight || document.documentElement.clientHeight;
      const updates = {};
      let changed = false;
      Object.entries(revealMap.current).forEach(([id, el]) => {
        if (!el || revealed[id]) return;
        if (el.getBoundingClientRect().top < vh * 0.92) {
          updates[id] = true;
          changed = true;
        }
      });
      if (changed) setRevealed((s) => ({ ...s, ...updates }));
    };
    window.addEventListener('scroll', check, { passive: true });
    window.addEventListener('resize', check);
    requestAnimationFrame(() => requestAnimationFrame(check));
    const t = setTimeout(check, 350);
    return () => {
      window.removeEventListener('scroll', check);
      window.removeEventListener('resize', check);
      clearTimeout(t);
    };
  }, [revealed]);

  const reveal = (id, extra = {}) => ({
    ref: register(id),
    style: {
      opacity: revealed[id] ? 1 : 0,
      transform: revealed[id] ? 'translateY(0)' : 'translateY(30px)',
      transition: 'opacity .8s ease, transform .8s ease',
      ...extra,
    },
  });

  const stagger = (id, i, extra = {}) => ({
    ref: register(id),
    style: {
      opacity: revealed[id] ? 1 : 0,
      transform: revealed[id] ? 'translateY(0)' : 'translateY(30px)',
      transition: `opacity .7s ease ${i * 0.09}s, transform .7s ease ${i * 0.09}s`,
      ...extra,
    },
  });

  const goApp = (e) => {
    e?.preventDefault?.();
    navigate('/app');
  };

  return (
    <div style={{ background: '#fafbfc', minHeight: '100vh' }}>
      <style>{`
        html, body { overflow-x: clip; }  /* clip (not hidden) → sticky still works */
        /* Nav anchor links must clear the sticky nav (~90px) so target headings
           don't hide behind it. Applied to every scroll target on the page. */
        [id="features"], [id="how"], [id="security"] { scroll-margin-top: 96px; }
        .lp-feature-card { transition: transform .3s ease; }
        .lp-feature-card:hover { transform: translateY(-6px); }
        .lp-anchor { color: #64748b; }
        .lp-anchor:hover { color: #0f172a; }
      `}</style>

      <div style={{ width: '100%', color: '#0f172a' }}>

        {/* NAV — flush to top of viewport */}
        <div className="lp-nav-wrap" style={{ position: 'sticky', top: 0, zIndex: 50, maxWidth: 1180, margin: '0 auto', padding: '12px 24px 0' }}>
          <div className="lp-nav-pill" style={{
            background: 'rgba(255,255,255,0.92)',
            backdropFilter: 'blur(14px)',
            WebkitBackdropFilter: 'blur(14px)',
            borderRadius: 18,
            boxShadow: '0 1px 0 rgba(15,23,42,0.05),0 8px 24px rgba(15,23,42,0.05)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 22px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <img
                src="/icarkno%20logo.png"
                alt="icarKno"
                style={{ width: 38, height: 38, flexShrink: 0, objectFit: 'contain', borderRadius: 11 }}
              />
              <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
                <span className="lp-nav-wordmark" style={{ fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 16.5 }}>Meeting Summariser</span>
                <span className="lp-nav-tagline" style={{ fontSize: 12, color: '#94a3b8' }}>by Carnot Research Pvt Ltd</span>
              </div>
            </div>
            <div className="lp-nav-links" style={{ display: 'flex', alignItems: 'center', gap: 34 }}>
              <a href="#features" className="lp-anchor" style={{ fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>Features</a>
              <a href="#how" className="lp-anchor" style={{ fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>How it works</a>
              <a href="#security" className="lp-anchor" style={{ fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>Security</a>
            </div>
          </div>
        </div>

        {/* HERO */}
        {(() => {
          const line1 = 'Every meeting';
          const line2 = 'Organised';
          const line3 = 'Actionable';
          const line4 = 'Accountable';
          const subText = 'AI-powered meeting intelligence that automatically creates summaries, assigns owners, tracks decisions, and captures deadlines.';
          const badgeStart = 0.05;
          const line1Start = 0.2;
          const line2Start = line1Start + line1.length * CHAR_STAGGER;
          const line3Start = line2Start + line2.length * CHAR_STAGGER;
          const line4Start = line3Start + line3.length * CHAR_STAGGER;
          const subStart   = line4Start + line4.length * CHAR_STAGGER + 0.05;
          const ctaDelay   = subStart + subText.length * CHAR_STAGGER + LETTER_REVEAL_DURATION * 0.4;
          return (
            <div className="lp-hero-grid" style={{
              maxWidth: 1180, margin: '0 auto', padding: '64px 24px 24px',
              display: 'grid', gridTemplateColumns: '1.05fr 1fr', gap: 56, alignItems: 'start',
            }}>
              <div>
                <div className="lp-hero-badge" style={{
                  opacity: 0,
                  animation: `wordReveal .55s cubic-bezier(0.22,1,0.36,1) ${badgeStart}s both`,
                  display: 'inline-flex', alignItems: 'center',
                  gap: 9, background: '#fafbfc', border: '1px solid #e2e8f0', borderRadius: 999,
                  padding: '9px 18px', fontSize: 13.5, fontWeight: 600, color: '#0d9488',
                }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#3fae63' }}></span>
                  On-premise · Your data never leaves your network
                </div>
                <h1 className="lp-hero-h1" style={{
                  fontFamily: "'Manrope',sans-serif",
                  fontWeight: 800, fontSize: 62, lineHeight: 1.06, letterSpacing: '-0.025em',
                  margin: '28px 0 24px', color: '#0f172a',
                }}>
                  <span style={{ display: 'block' }}>
                    <Words text={line1} delay={line1Start} />
                  </span>
                  <span style={{ display: 'block' }}>
                    <Words text={line2} delay={line2Start} />
                  </span>
                  <span style={{ display: 'block' }}>
                    <Words text={line3} delay={line3Start} />
                  </span>
                  <span style={{ display: 'block' }}>
                    <Words text={line4} color="#0d9488" delay={line4Start} />
                  </span>
                </h1>
                <p className="lp-hero-sub" style={{
                  fontSize: 18.5, lineHeight: 1.6,
                  color: '#64748b', maxWidth: 480, margin: '0 0 36px',
                }}>
                  <Words text={subText} delay={subStart} />
                </p>
                <div className="lp-hero-ctas" style={{
                  opacity: 0,
                  animation: `wordReveal .55s cubic-bezier(0.22,1,0.36,1) ${ctaDelay.toFixed(2)}s both`,
                  display: 'flex', gap: 16, alignItems: 'center',
                }}>
                  <a
                    href="/app"
                    onClick={goApp}
                    onMouseEnter={() => setCtaHover(true)}
                    onMouseLeave={() => setCtaHover(false)}
                    style={{
                      display: 'inline-block', background: '#0f172a', color: '#ffffff',
                      borderRadius: 14, padding: '17px 34px', fontSize: 16.5, fontWeight: 700,
                      cursor: 'pointer', textDecoration: 'none',
                      boxShadow: ctaHover ? '0 18px 36px rgba(15,23,42,0.28)' : '0 12px 28px rgba(15,23,42,0.22)',
                      transform: ctaHover ? 'translateY(-3px)' : 'translateY(0)',
                      transition: 'transform .25s ease, box-shadow .25s ease',
                    }}
                  >Explore Product →</a>
                  <a href="#how" style={{ fontSize: 16, fontWeight: 600, padding: '16px 10px', color: '#0f172a', textDecoration: 'none' }}>See how it works</a>
                </div>
              </div>

              <div style={{ animation: 'fadeUp .9s ease .3s both' }}>
                <img
                  src="/image.png"
                  alt="Meeting summary preview"
                  style={{
                    width: '100%',
                    display: 'block',
                  }}
                />
              </div>
            </div>
          );
        })()}

        {/* MARQUEE */}
        <div style={{
          borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0',
          marginTop: 40, overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', flexWrap: 'nowrap',
            gap: 36, padding: '22px 0', lineHeight: 1, width: 'max-content',
            animation: 'marqueeScroll 26s linear infinite',
          }}>
            {marqueeItems.map((m, i) => (
              <React.Fragment key={i}>
                <span style={{
                  fontFamily: "'Manrope',sans-serif", fontWeight: 700, fontSize: 15.5,
                  color: '#94a3b8', lineHeight: 1, whiteSpace: 'nowrap',
                }}>{m}</span>
                <span style={{
                  color: '#0d9488', fontSize: 14, lineHeight: 1, flexShrink: 0,
                }}>✦</span>
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* FEATURES — sticky pinned heading + stacking cards */}
        <FeaturesSection features={features} />


        {/* HOW IT WORKS — horizontal flow with product mockups */}
        <HowItWorks steps={steps} reveal={reveal} stagger={stagger} />

        {/* SECURITY */}
        <div id="security" {...reveal('security', {
          maxWidth: 1180, margin: '112px auto 0', padding: '0 24px', boxSizing: 'border-box',
        })}>
          <div style={{
            background: '#0f172a', borderRadius: 28, padding: '64px',
            display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 48, alignItems: 'center',
          }} className="lp-security-card">
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.1em', color: '#0d9488', marginBottom: 14 }}>SECURITY FIRST</div>
              <h3 className="lp-security-h3" style={{
                fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 36, color: '#ffffff',
                margin: '0 0 16px', lineHeight: 1.2, letterSpacing: '-0.015em',
              }}>Your meetings never leave your network</h3>
              <p style={{ fontSize: 16, lineHeight: 1.7, color: '#94a3b8', margin: 0 }}>
                Every recording, transcript, and summary is processed on your own infrastructure — no third-party APIs, no external retention, no exceptions.
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {securityPoints.map((p, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 14, alignItems: 'flex-start',
                  background: '#1e293b', borderRadius: 14, padding: '18px 20px',
                }}>
                  <div style={{ color: '#0d9488', fontSize: 16, marginTop: 1 }}>✓</div>
                  <div style={{ fontSize: 15, color: '#cbd5e1', lineHeight: 1.55 }}>{p}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* CTA */}
        <div {...reveal('cta', {
          maxWidth: 1180, margin: '112px auto 0', padding: '0 24px', textAlign: 'center',
        })} className="lp-cta">
          <h2 style={{
            fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 44,
            letterSpacing: '-0.02em', margin: '0 0 18px',
          }}>Turn your next meeting<br />into clear action.</h2>
          <p style={{ fontSize: 17, color: '#64748b', margin: '0 0 36px' }}>Deploy on your own servers in under a day.</p>
          <a
            href="/app"
            onClick={goApp}
            onMouseEnter={() => setBigCtaHover(true)}
            onMouseLeave={() => setBigCtaHover(false)}
            style={{
              display: 'inline-block', background: '#0f172a', color: '#ffffff',
              borderRadius: 14, padding: '17px 34px', fontSize: 16.5, fontWeight: 700,
              cursor: 'pointer', textDecoration: 'none',
              boxShadow: bigCtaHover ? '0 18px 36px rgba(15,23,42,0.28)' : '0 12px 28px rgba(15,23,42,0.22)',
              transform: bigCtaHover ? 'translateY(-3px)' : 'translateY(0)',
              transition: 'transform .25s ease, box-shadow .25s ease',
            }}
          >Explore the Product →</a>
        </div>

        {/* FOOTER */}
        <div className="lp-footer" style={{
          maxWidth: 1180, margin: '112px auto 0', padding: '36px 24px 44px',
          borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', flexWrap: 'wrap', gap: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <img
              src="/icarkno%20logo.png"
              alt="icarKno"
              style={{ width: 34, height: 34, flexShrink: 0, objectFit: 'contain', borderRadius: 10 }}
            />
            <span style={{ fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 15.5 }}>Carnot Research</span>
          </div>
          <div className="lp-footer-links" style={{ display: 'flex', gap: 30 }}>
            <a href="#features" className="lp-anchor" style={{ fontSize: 14.5, textDecoration: 'none' }}>Features</a>
            <a href="#how" className="lp-anchor" style={{ fontSize: 14.5, textDecoration: 'none' }}>How it works</a>
            <a href="#security" className="lp-anchor" style={{ fontSize: 14.5, textDecoration: 'none' }}>Security</a>
          </div>
          <div style={{ fontSize: 13.5, color: '#94a3b8' }}>© 2026 Carnot Research</div>
        </div>

      </div>
    </div>
  );
}
