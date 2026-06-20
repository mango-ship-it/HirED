import React, { useState, useEffect, useRef } from 'react';

// ─── Placeholder lessons ──────────────────────────────────────────────────────
// TODO: Replace with real `lessons` array from /score API response.
// Shape expected: { id, category, fix, text }[]
const PLACEHOLDER_LESSONS = [
  {
    id: 'l1',
    category: 'Quantified Impact',
    fix: 'Add a number to every bullet that describes work you did.',
    text: 'Temporary lesson text — replace with real content from the /score response. Your bullets describe what you did, but not at what scale. Recruiters need magnitude to understand your impact. "Managed a team" becomes "Managed an eight-person team that shipped three features in Q2." Every action you describe should have a number that proves its scope.',
  },
  {
    id: 'l2',
    category: 'Skills Match',
    fix: 'Mirror the exact keywords from the job description.',
    text: 'Temporary lesson text — replace with real content from the /score response. Applicant tracking systems scan for exact phrases before a human ever reads your resume. If the job posting says "cross-functional collaboration" and your resume says "worked with other teams," you become invisible to the first filter. Lift their language precisely — do not paraphrase it.',
  },
  {
    id: 'l3',
    category: 'Clarity',
    fix: 'Lead every bullet with a strong past-tense action verb.',
    text: 'Temporary lesson text — replace with real content from the /score response. Phrases like "responsible for" or "assisted with" read as passive and waste precious characters. Start each bullet with Built, Led, Reduced, or Launched. Recruiters spend roughly six seconds on a resume during the first pass — every single word must earn its place on the page.',
  },
];

// ─── Types ────────────────────────────────────────────────────────────────────
export type Lesson = {
  id: string;
  category: string;
  fix: string;
  text: string;
};

type Props = {
  lessons?: Lesson[];
  onExit?: () => void;
};

// ─── Word-span renderer ───────────────────────────────────────────────────────
// Splits text into word tokens and renders each with spoken/current/unspoken style.
function WordSpans({ text, spokenChar }: { text: string; spokenChar: number }) {
  type Token = { kind: 'word' | 'space'; value: string; start: number };
  const tokens: Token[] = [];
  const re = /(\S+)/g;
  let cursor = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) {
      tokens.push({ kind: 'space', value: text.slice(cursor, m.index), start: cursor });
    }
    tokens.push({ kind: 'word', value: m[0], start: m.index });
    cursor = m.index + m[0].length;
  }
  if (cursor < text.length) {
    tokens.push({ kind: 'space', value: text.slice(cursor), start: cursor });
  }

  return (
    <>
      {tokens.map((tok) => {
        const end = tok.start + tok.value.length;
        const spoken = end <= spokenChar;
        const current = tok.kind === 'word' && tok.start <= spokenChar && end > spokenChar;
        return (
          <span
            key={tok.start}
            className={
              current
                ? 'bg-yellow-200 text-gray-900 rounded px-0.5'
                : spoken
                ? 'opacity-35'
                : ''
            }
          >
            {tok.value}
          </span>
        );
      })}
    </>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function LessonPage({ lessons = PLACEHOLDER_LESSONS, onExit }: Props) {
  const [idx, setIdx] = useState(0);
  const [spokenChar, setSpokenChar] = useState(0);
  const [barProgress, setBarProgress] = useState<number[]>(() => lessons.map(() => 0));
  const [visible, setVisible] = useState(true);
  const [qOpen, setQOpen] = useState(false);
  const [qInput, setQInput] = useState('');
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  // Refs that let speech callbacks read current values without stale closures
  const speakFnRef = useRef<(fromChar: number) => void>(() => {});
  const spokenCharRef = useRef(0);
  const pausedAtRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { spokenCharRef.current = spokenChar; }, [spokenChar]);

  const lesson = lessons[idx];

  // ── Narration effect ────────────────────────────────────────────────────────
  // Re-runs whenever the active lesson index changes.
  useEffect(() => {
    const currentIdx = idx;
    const text = lessons[currentIdx].text;

    function speakFrom(fromChar: number) {
      window.speechSynthesis.cancel();
      if (timerRef.current) clearTimeout(timerRef.current);

      const slice = text.substring(fromChar);
      if (!slice.trim()) return;

      const utt = new SpeechSynthesisUtterance(slice);

      utt.onboundary = (e) => {
        const abs = fromChar + e.charIndex;
        setSpokenChar(abs);
        setBarProgress((prev) => {
          const next = [...prev];
          next[currentIdx] = Math.min(1, abs / text.length);
          return next;
        });
      };

      utt.onend = () => {
        setBarProgress((prev) => {
          const next = [...prev];
          next[currentIdx] = 1;
          return next;
        });
        // Auto-advance to next lesson after a short breath
        timerRef.current = setTimeout(() => {
          if (currentIdx < lessons.length - 1) {
            setVisible(false);
            setTimeout(() => {
              setIdx(currentIdx + 1);
              setSpokenChar(0);
              pausedAtRef.current = 0;
              setSubmitted(null);
              setQOpen(false);
              setVisible(true);
            }, 300);
          }
        }, 1500);
      };

      window.speechSynthesis.speak(utt);
    }

    speakFnRef.current = speakFrom;
    setSpokenChar(0);
    pausedAtRef.current = 0;
    speakFrom(0);

    return () => {
      window.speechSynthesis.cancel();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [idx]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Interrupt: ask a question ───────────────────────────────────────────────
  const handleAsk = () => {
    window.speechSynthesis.cancel();
    if (timerRef.current) clearTimeout(timerRef.current);
    pausedAtRef.current = spokenCharRef.current;
    setQOpen(true);
    setSubmitted(null);
    setQInput('');
  };

  const handleSubmitQ = (e: React.FormEvent) => {
    e.preventDefault();
    if (!qInput.trim()) return;
    setSubmitted(qInput.trim());
    setQInput('');
  };

  // Resume from exactly where speech was interrupted
  const handleDismiss = () => {
    setSubmitted(null);
    setQOpen(false);
    speakFnRef.current(pausedAtRef.current);
  };

  // ── Jump to lesson via progress bar click ───────────────────────────────────
  const jumpTo = (i: number) => {
    if (i === idx) return;
    window.speechSynthesis.cancel();
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
    setTimeout(() => {
      setIdx(i);
      setSpokenChar(0);
      setSubmitted(null);
      setQOpen(false);
      setVisible(true);
    }, 300);
  };

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col select-none">

      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <header className="shrink-0 flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-widest text-gray-500">
            {lesson.category}
          </span>
          {/* Visible PLACEHOLDER marker — remove once real data is wired */}
          <span className="text-[10px] font-mono bg-amber-100 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5 leading-tight">
            PLACEHOLDER
          </span>
        </div>

        <div className="flex items-center gap-1">
          {/* Flag / report */}
          <button
            title="Report an issue"
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18m0-13h14l-2 4 2 4H3" />
            </svg>
          </button>
          {/* Exit */}
          <button
            onClick={onExit}
            title="Exit lessons"
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </header>

      {/* ── Center stage ────────────────────────────────────────────────────── */}
      <main className="flex-1 flex items-center justify-center px-8 overflow-hidden">
        <div
          className={`max-w-2xl w-full transition-all duration-300 ease-out ${
            visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'
          }`}
        >
          {/* Category chip */}
          <div className="mb-5">
            <span className="inline-flex items-center gap-2 bg-gray-100 text-gray-700 text-sm font-semibold px-3 py-1.5 rounded-lg">
              {lesson.category}
              {/* [TEMP] label beside category in the card as well */}
              <span className="text-[9px] font-mono text-gray-400 font-normal">[TEMP]</span>
            </span>
          </div>

          {/* The fix */}
          <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1">The fix</p>
          <p className="text-base font-semibold text-gray-700 mb-7">{lesson.fix}</p>

          {/* Narrated explanation — words light up as they're spoken */}
          <p className="text-xl leading-relaxed text-gray-800">
            <WordSpans text={lesson.text} spokenChar={spokenChar} />
          </p>

          {/* ── Q&A inline panel ─────────────────────────────────────────── */}
          {qOpen && (
            <div className="mt-8 border border-gray-200 rounded-2xl p-5 bg-gray-50">
              {submitted ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1">Your question</p>
                    <p className="text-sm text-gray-700 italic">"{submitted}"</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1">Answer</p>
                    {/* TODO: replace thinking state with real API response */}
                    <p className="text-sm text-gray-400 animate-pulse">thinking…</p>
                  </div>
                  <button
                    onClick={handleDismiss}
                    className="text-xs text-gray-400 hover:text-gray-700 underline underline-offset-2 transition-colors"
                  >
                    Resume lesson →
                  </button>
                </div>
              ) : (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-3">Ask about this lesson</p>
                  <form onSubmit={handleSubmitQ} className="flex gap-2">
                    <input
                      autoFocus
                      value={qInput}
                      onChange={(e) => setQInput(e.target.value)}
                      placeholder="What would you like to know?"
                      className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-gray-300 bg-white"
                    />
                    <button
                      type="submit"
                      className="text-sm px-4 py-2 bg-gray-900 text-white rounded-xl hover:bg-gray-700 transition-colors"
                    >
                      Send
                    </button>
                  </form>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* ── Persistent ask button ────────────────────────────────────────────── */}
      <div className="shrink-0 flex justify-center pb-3">
        <button
          onClick={handleAsk}
          className="text-xs text-gray-400 hover:text-gray-700 border border-gray-200 hover:border-gray-400 rounded-full px-4 py-1.5 transition-colors"
        >
          {qOpen ? 'Question panel is open ↑' : 'Ask a question'}
        </button>
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
      <footer className="shrink-0 px-6 pb-6 pt-1">
        <div className="flex items-center gap-4">

          {/* Mascot + chat toggle */}
          <div className="flex items-center gap-2 shrink-0">
            {/* TODO: replace with real mascot/avatar component */}
            <div className="w-10 h-10 rounded-xl bg-gray-100 border border-gray-200 flex items-center justify-center text-base">
              🎓
            </div>
            <button
              onClick={() => setChatOpen((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-800 border border-gray-200 hover:border-gray-400 rounded-full px-3 py-1 transition-colors"
            >
              {chatOpen ? 'Close chat' : 'Open chat'}
            </button>
          </div>

          {/* Progress bars — one per lesson */}
          <div className="flex-1 flex gap-2 items-end">
            {lessons.map((l, i) => {
              const pct = i < idx ? 1 : i === idx ? barProgress[i] : 0;
              return (
                <div
                  key={l.id}
                  className="relative flex-1 cursor-pointer"
                  onMouseEnter={() => setHoveredBar(i)}
                  onMouseLeave={() => setHoveredBar(null)}
                  onClick={() => jumpTo(i)}
                >
                  {/* Tooltip — only the hovered bar shows its label */}
                  {hoveredBar === i && (
                    <div
                      role="tooltip"
                      className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap bg-gray-900 text-white text-xs rounded-lg px-2.5 py-1 pointer-events-none z-10"
                    >
                      {l.category}
                      {/* Tooltip arrow */}
                      <span className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-gray-900" />
                    </div>
                  )}
                  {/* Bar track + fill */}
                  <div className="h-1 w-full bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gray-700 rounded-full transition-[width] duration-100 ease-linear"
                      style={{ width: `${pct * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </footer>

    </div>
  );
}
