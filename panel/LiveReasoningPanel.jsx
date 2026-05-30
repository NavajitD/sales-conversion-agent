import React, { useReducer, useEffect, useRef, useCallback } from "react";
import {
  PhoneCall, Activity, Brain, TrendingUp, Play, RotateCcw,
  CheckCircle2, Quote, ChevronRight, Radio
} from "lucide-react";

/* ------------------------------------------------------------------ *
 * PS4 LIVE REASONING PANEL
 * Consumes the `log_call_state` object emitted by the voice agent.
 * Wire live data by calling ingest(event) on each function call from
 * your Vapi/Retell webhook. A scripted demo plays the same path so the
 * stage demo never depends on the live wiring holding up.
 * ------------------------------------------------------------------ */

const CLASS_META = {
  positive:  { label: "POSITIVE",  color: "#34D399", glow: "rgba(52,211,153,.18)" },
  soft_no:   { label: "SOFT NO",   color: "#F5A524", glow: "rgba(245,165,36,.18)" },
  ambiguous: { label: "AMBIGUOUS", color: "#5B8DEF", glow: "rgba(91,141,239,.18)" },
  hard_no:   { label: "HARD NO",   color: "#F2555A", glow: "rgba(242,85,90,.18)" },
  idle:      { label: "STANDBY",   color: "#7A8699", glow: "rgba(122,134,153,.12)" },
};

const STRATEGY_LABELS = {
  payment_plan: "Payment plan",
  value_roi_reframe: "Value / ROI reframe",
  competitor_differentiation: "Competitor differentiation",
  second_session_offer: "Second-session offer",
  experience_rediagnosis: "Experience re-diagnosis",
  equip_internal_sell: "Equip internal sell",
  disambiguation_probe: "Disambiguation probe",
  cost_of_delay: "Cost-of-delay reframe",
  social_proof: "Social proof",
  accountability_proof: "Accountability proof",
  flexible_scheduling: "Flexible scheduling",
  direct_close: "Direct close",
  graceful_exit: "Graceful exit",
};

const OBJ_LABELS = {
  price: "Price / affordability",
  comparison: "Competitor comparison",
  child_experience: "Child experience",
  spouse_deferral: "Spouse deferral",
  stalling: "Stalling",
  timing: "Timing",
  trust: "Trust",
  logistics: "Logistics",
  none: "None",
};

const SENTIMENT_PCT = { hostile: 8, cold: 30, neutral: 55, warm: 88 };
const SENTIMENT_LABEL = { hostile: "Hostile", cold: "Cold", neutral: "Neutral", warm: "Warm" };

/* The winning 90-second story: ambiguous -> price (split) -> warm -> booked. */
const DEMO_SCRIPT = [
  {
    after: 1200,
    utterance: "Haan dekha tha... accha tha. Par abhi sochna padega.",
    objection_primary: "stalling",
    objection_verbatim: "accha tha, par sochna padega",
    intent_classification: "ambiguous",
    intent_confidence: 0.56,
    strategy_applied: "disambiguation_probe",
    sentiment: "neutral",
  },
  {
    after: 6000,
    utterance: "Dekhiye sach kahun toh fees thodi zyada lag rahi hai.",
    objection_primary: "price",
    objection_verbatim: "fees thodi zyada lag rahi hai",
    intent_classification: "soft_no",
    intent_confidence: 0.79,
    strategy_applied: "value_roi_reframe",
    sentiment: "cold",
  },
  {
    after: 6000,
    utterance: "Value to samajh aata hai, bas ek saath dena heavy lagta hai.",
    objection_primary: "price",
    objection_verbatim: "ek saath dena heavy lagta hai",
    intent_classification: "soft_no",
    intent_confidence: 0.83,
    strategy_applied: "payment_plan",
    sentiment: "neutral",
  },
  {
    after: 6000,
    utterance: "Theek hai. Ek aur demo ho sakta hai alag teacher ke saath?",
    objection_primary: "none",
    objection_verbatim: "ek aur demo ho sakta hai alag teacher ke saath?",
    intent_classification: "positive",
    intent_confidence: 0.74,
    strategy_applied: "second_session_offer",
    sentiment: "warm",
  },
  {
    after: 5000,
    final: true,
    intent_classification: "positive",
    intent_confidence: 0.86,
    sentiment: "warm",
    next_step: "second_session_booked",
    next_step_label: "Second session booked",
    next_step_time: "Tomorrow, 6:00 PM – with Ms. Kapoor (Physics)",
    objection_verbatim: "fees thodi zyada lag rahi hai",
    counselor_notes:
      "Price-sensitive but value-convinced. Resisted lump-sum, opened to payment plan. Booked 2nd demo to re-confirm fit before enrolment push.",
  },
];

const CONTEXT = {
  parent: "Mr. Sharma",
  child: "Aarav",
  meta: "Class 11 · CBSE · JEE 2027",
  demo: "Physics demo · today 4:00 PM",
  weak: "Rotational Motion",
};

/* ------------------------------- state ------------------------------- */
const initial = { status: "idle", turns: [], current: null, finalCard: null, elapsed: 0 };

function reducer(state, action) {
  switch (action.type) {
    case "reset":
      return { ...initial };
    case "start":
      return { ...initial, status: "live" };
    case "tick":
      return { ...state, elapsed: state.elapsed + 1 };
    case "turn": {
      const turn = { ...action.payload, id: state.turns.length, t: state.elapsed };
      return { ...state, turns: [turn, ...state.turns], current: turn };
    }
    case "final":
      return {
        ...state,
        status: "ended",
        current: state.current ? { ...state.current, ...action.payload } : action.payload,
        finalCard: action.payload,
      };
    default:
      return state;
  }
}

/* ------------------------------ component ----------------------------- */
export default function LiveReasoningPanel() {
  const [state, dispatch] = useReducer(reducer, initial);
  const timers = useRef([]);
  const tickRef = useRef(null);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = null;
  };

  /* live seam: call this from your webhook for real calls */
  const ingest = useCallback((event) => {
    if (event.final) dispatch({ type: "final", payload: event });
    else dispatch({ type: "turn", payload: event });
  }, []);

  useEffect(() => {
    window.__ingestCallState = ingest; // <-- wire your Vapi/Retell webhook here
    return () => { delete window.__ingestCallState; };
  }, [ingest]);

  const runDemo = () => {
    clearTimers();
    dispatch({ type: "reset" });
    dispatch({ type: "start" });
    tickRef.current = setInterval(() => dispatch({ type: "tick" }), 1000);
    let acc = 0;
    DEMO_SCRIPT.forEach((ev) => {
      acc += ev.after;
      timers.current.push(setTimeout(() => ingest(ev), acc));
    });
    timers.current.push(setTimeout(() => { if (tickRef.current) clearInterval(tickRef.current); }, acc + 200));
  };

  useEffect(() => clearTimers, []);

  const reset = () => { clearTimers(); dispatch({ type: "reset" }); };

  const cls = CLASS_META[state.current?.intent_classification || "idle"];
  const conf = Math.round((state.current?.intent_confidence || 0) * 100);
  const sentiment = state.current?.sentiment || (state.status === "idle" ? null : "neutral");
  const mm = String(Math.floor(state.elapsed / 60)).padStart(2, "0");
  const ss = String(state.elapsed % 60).padStart(2, "0");

  return (
    <div style={S.root}>
      <style>{CSS}</style>

      {/* header */}
      <div style={S.header}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={S.brandMark}><PhoneCall size={16} strokeWidth={2.4} color="#0B0E14" /></div>
          <div>
            <div style={S.brandName}>ARIA &middot; POST-DEMO CONVERSION</div>
            <div style={S.brandSub}>{CONTEXT.parent} &middot; re: {CONTEXT.child} &middot; {CONTEXT.meta}</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{
              ...S.liveDot,
              background: state.status === "live" ? "#34D399" : state.status === "ended" ? "#7A8699" : "#3A4150",
              animation: state.status === "live" ? "pulse 1.4s infinite" : "none",
            }} />
            <span style={S.liveLabel}>
              {state.status === "live" ? "LIVE" : state.status === "ended" ? "ENDED" : "STANDBY"}
            </span>
          </div>
          <span style={S.timer}>{mm}:{ss}</span>
        </div>
      </div>

      {/* body grid */}
      <div style={S.grid}>
        {/* LEFT: NOW + sentiment + (card | controls) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* NOW panel */}
          <div style={{ ...S.card, boxShadow: `inset 0 0 0 1px ${cls.color}33, 0 0 32px ${cls.glow}` }}>
            <div style={S.cardLabel}><Brain size={12} /> CURRENT READ</div>
            <div style={S.nowPill(cls)}>{cls.label}</div>

            <div style={S.confRow}>
              <span style={S.confLabel}>confidence</span>
              <span style={{ ...S.confVal, color: cls.color }}>{conf}%</span>
            </div>
            <div style={S.confTrack}>
              <div style={{ ...S.confFill, width: `${conf}%`, background: cls.color }} />
            </div>

            <div style={S.divider} />

            <div style={S.kv}>
              <span style={S.k}>strategy</span>
              <span style={S.v}>
                {state.current?.strategy_applied
                  ? STRATEGY_LABELS[state.current.strategy_applied]
                  : <span style={{ color: "#4A5163" }}>&mdash;</span>}
              </span>
            </div>
            <div style={S.kv}>
              <span style={S.k}>objection</span>
              <span style={S.v}>
                {state.current?.objection_primary
                  ? OBJ_LABELS[state.current.objection_primary]
                  : <span style={{ color: "#4A5163" }}>&mdash;</span>}
              </span>
            </div>

            {state.current?.objection_verbatim && (
              <div style={S.quote}>
                <Quote size={13} color={cls.color} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>"{state.current.objection_verbatim}"</span>
              </div>
            )}
          </div>

          {/* sentiment arc */}
          <div style={S.card}>
            <div style={S.cardLabel}><TrendingUp size={12} /> SENTIMENT ARC</div>
            <div style={S.arcTrack}>
              <div style={S.arcGradient} />
              {sentiment && (
                <div style={{ ...S.arcMarker, left: `${SENTIMENT_PCT[sentiment]}%` }}>
                  <div style={S.arcDot} />
                  <div style={S.arcTag}>{SENTIMENT_LABEL[sentiment]}</div>
                </div>
              )}
            </div>
            <div style={S.arcScale}>
              <span>Hostile</span><span>Cold</span><span>Neutral</span><span>Warm</span>
            </div>
          </div>

          {/* CRM card on end, else controls */}
          {state.finalCard ? (
            <div style={{ ...S.card, ...S.crmCard }}>
              <div style={{ ...S.cardLabel, color: "#34D399" }}><CheckCircle2 size={13} /> CRM CARD &middot; AUTO-FILLED</div>
              <div style={S.crmStep}>{state.finalCard.next_step_label}</div>
              <div style={S.crmTime}>{state.finalCard.next_step_time}</div>
              <div style={S.crmQuote}>
                <span style={S.crmQuoteLabel}>KEY OBJECTION (VERBATIM)</span>
                "{state.finalCard.objection_verbatim}"
              </div>
              <div style={S.crmNotesLabel}>COUNSELOR NOTES</div>
              <div style={S.crmNotes}>{state.finalCard.counselor_notes}</div>
            </div>
          ) : (
            <div style={S.controls}>
              <button onClick={runDemo} style={S.primaryBtn} disabled={state.status === "live"}>
                <Play size={15} /> {state.status === "live" ? "Running…" : "Run demo call"}
              </button>
              <button onClick={reset} style={S.ghostBtn}><RotateCcw size={14} /> Reset</button>
            </div>
          )}
          {state.finalCard && (
            <button onClick={reset} style={S.ghostBtn}><RotateCcw size={14} /> Reset</button>
          )}
        </div>

        {/* RIGHT: reasoning timeline */}
        <div style={{ ...S.card, display: "flex", flexDirection: "column", minHeight: 420 }}>
          <div style={S.cardLabel}><Activity size={12} /> REASONING TIMELINE</div>
          {state.turns.length === 0 ? (
            <div style={S.empty}>
              <Radio size={26} color="#2C3340" />
              <span>Waiting for the call to begin.</span>
              <span style={{ fontSize: 11, color: "#3A4150" }}>Each parent turn appends a reasoning step.</span>
            </div>
          ) : (
            <div style={S.feed}>
              {state.turns.map((turn) => {
                const m = CLASS_META[turn.intent_classification];
                return (
                  <div key={turn.id} style={S.turn} className="aria-turn">
                    <div style={{ ...S.turnRail, background: m.color }} />
                    <div style={S.turnBody}>
                      <div style={S.turnTop}>
                        <span style={S.turnUtter}>"{turn.utterance}"</span>
                        <span style={S.turnTime}>
                          {String(Math.floor(turn.t / 60)).padStart(2, "0")}:{String(turn.t % 60).padStart(2, "0")}
                        </span>
                      </div>
                      <div style={S.chips}>
                        <span style={S.chip(m.color)}>{m.label} &middot; {Math.round(turn.intent_confidence * 100)}%</span>
                        {turn.objection_primary && turn.objection_primary !== "none" && (
                          <span style={S.chipMuted}>{OBJ_LABELS[turn.objection_primary]}</span>
                        )}
                        <ChevronRight size={12} color="#4A5163" />
                        <span style={S.chipStrat}>{STRATEGY_LABELS[turn.strategy_applied]}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div style={S.footer}>
        Live wiring seam: <code style={S.code}>window.__ingestCallState(event)</code> &mdash; call it from your Vapi/Retell function webhook with the <code style={S.code}>log_call_state</code> payload. The demo button replays the same path.
      </div>
    </div>
  );
}

/* ------------------------------- styles ------------------------------ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.82)} }
@keyframes slideIn { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
.aria-turn{ animation: slideIn .35s cubic-bezier(.2,.7,.3,1) }
* { box-sizing: border-box; }
`;

const mono = "'IBM Plex Mono', monospace";
const sans = "'Archivo', sans-serif";

const S = {
  root: { background: "#0B0E14", color: "#E8ECF4", fontFamily: sans, borderRadius: 16, padding: 18, border: "1px solid #1A2030", maxWidth: 920, margin: "0 auto" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 14, borderBottom: "1px solid #1A2030", marginBottom: 14 },
  brandMark: { width: 32, height: 32, borderRadius: 9, background: "#34D399", display: "grid", placeItems: "center", boxShadow: "0 0 18px rgba(52,211,153,.4)" },
  brandName: { fontSize: 12.5, fontWeight: 800, letterSpacing: 1.2 },
  brandSub: { fontSize: 11, color: "#8B96A8", fontFamily: mono, marginTop: 2 },
  liveDot: { width: 9, height: 9, borderRadius: "50%" },
  liveLabel: { fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: "#8B96A8" },
  timer: { fontFamily: mono, fontSize: 15, fontWeight: 600, color: "#E8ECF4" },

  grid: { display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.1fr)", gap: 14 },

  card: { background: "#11151F", border: "1px solid #1E2533", borderRadius: 13, padding: 15 },
  cardLabel: { display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, fontWeight: 700, letterSpacing: 1.4, color: "#7A8699", marginBottom: 13 },

  nowPill: (c) => ({ display: "inline-block", fontSize: 22, fontWeight: 800, letterSpacing: 1.5, color: c.color, padding: "8px 16px", borderRadius: 9, background: c.glow, border: `1px solid ${c.color}40` }),

  confRow: { display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 16, marginBottom: 6 },
  confLabel: { fontSize: 10.5, letterSpacing: 1, color: "#7A8699", fontFamily: mono, textTransform: "uppercase" },
  confVal: { fontFamily: mono, fontSize: 16, fontWeight: 600 },
  confTrack: { height: 6, background: "#1A2030", borderRadius: 4, overflow: "hidden" },
  confFill: { height: "100%", borderRadius: 4, transition: "width .6s cubic-bezier(.2,.7,.3,1), background .4s" },

  divider: { height: 1, background: "#1A2030", margin: "15px 0" },
  kv: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0" },
  k: { fontSize: 11, color: "#7A8699", fontFamily: mono, letterSpacing: .5 },
  v: { fontSize: 13, fontWeight: 600, color: "#E8ECF4", textAlign: "right" },

  quote: { display: "flex", gap: 8, marginTop: 13, padding: "10px 12px", background: "#0E1219", borderRadius: 9, fontSize: 13, lineHeight: 1.45, color: "#C3CCDB", fontStyle: "italic", border: "1px solid #1A2030" },

  arcTrack: { position: "relative", height: 12, borderRadius: 6, marginBottom: 26, marginTop: 6 },
  arcGradient: { position: "absolute", inset: 0, borderRadius: 6, background: "linear-gradient(90deg,#F2555A 0%,#5B8DEF 35%,#7A8699 58%,#34D399 100%)", opacity: .85 },
  arcMarker: { position: "absolute", top: -4, transform: "translateX(-50%)", transition: "left .7s cubic-bezier(.2,.7,.3,1)", display: "flex", flexDirection: "column", alignItems: "center" },
  arcDot: { width: 20, height: 20, borderRadius: "50%", background: "#fff", border: "3px solid #0B0E14", boxShadow: "0 2px 8px rgba(0,0,0,.5)" },
  arcTag: { marginTop: 6, fontSize: 10.5, fontWeight: 700, fontFamily: mono, color: "#E8ECF4", whiteSpace: "nowrap" },
  arcScale: { display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "#5A6478", fontFamily: mono, letterSpacing: .5 },

  controls: { display: "flex", gap: 10 },
  primaryBtn: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#34D399", color: "#0B0E14", border: "none", borderRadius: 11, padding: "13px 16px", fontSize: 14, fontWeight: 700, fontFamily: sans, cursor: "pointer" },
  ghostBtn: { display: "flex", alignItems: "center", justifyContent: "center", gap: 7, background: "transparent", color: "#8B96A8", border: "1px solid #232B3A", borderRadius: 11, padding: "13px 16px", fontSize: 13, fontWeight: 600, fontFamily: sans, cursor: "pointer" },

  crmCard: { boxShadow: "inset 0 0 0 1px rgba(52,211,153,.25), 0 0 30px rgba(52,211,153,.1)", animation: "slideIn .5s ease" },
  crmStep: { fontSize: 18, fontWeight: 800, color: "#34D399", marginBottom: 4 },
  crmTime: { fontSize: 12.5, color: "#C3CCDB", fontFamily: mono, marginBottom: 14 },
  crmQuote: { fontSize: 13, fontStyle: "italic", color: "#C3CCDB", padding: "10px 12px", background: "#0E1219", borderRadius: 9, border: "1px solid #1A2030", marginBottom: 13 },
  crmQuoteLabel: { display: "block", fontSize: 9, letterSpacing: 1.2, color: "#5A6478", fontStyle: "normal", fontFamily: mono, marginBottom: 5 },
  crmNotesLabel: { fontSize: 9, letterSpacing: 1.2, color: "#5A6478", fontFamily: mono, marginBottom: 5 },
  crmNotes: { fontSize: 12.5, lineHeight: 1.5, color: "#AEB8C8" },

  empty: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, color: "#5A6478", fontSize: 13, textAlign: "center" },
  feed: { display: "flex", flexDirection: "column", gap: 10, overflowY: "auto", maxHeight: 380, paddingRight: 4 },
  turn: { display: "flex", gap: 10 },
  turnRail: { width: 3, borderRadius: 2, flexShrink: 0 },
  turnBody: { flex: 1, background: "#0E1219", border: "1px solid #1A2030", borderRadius: 10, padding: "10px 12px" },
  turnTop: { display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 9 },
  turnUtter: { fontSize: 12.5, color: "#C3CCDB", fontStyle: "italic", lineHeight: 1.4 },
  turnTime: { fontFamily: mono, fontSize: 10.5, color: "#5A6478", flexShrink: 0 },
  chips: { display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" },
  chip: (c) => ({ fontSize: 10.5, fontWeight: 700, fontFamily: mono, letterSpacing: .5, color: c, background: `${c}1A`, border: `1px solid ${c}40`, borderRadius: 6, padding: "3px 8px" }),
  chipMuted: { fontSize: 10.5, fontFamily: mono, color: "#8B96A8", background: "#161C2A", border: "1px solid #232B3A", borderRadius: 6, padding: "3px 8px" },
  chipStrat: { fontSize: 10.5, fontWeight: 600, fontFamily: mono, color: "#E8ECF4", background: "#1A2233", border: "1px solid #2A3344", borderRadius: 6, padding: "3px 8px" },

  footer: { marginTop: 14, paddingTop: 13, borderTop: "1px solid #1A2030", fontSize: 11, color: "#5A6478", lineHeight: 1.5 },
  code: { fontFamily: mono, color: "#8B96A8", background: "#11151F", padding: "1px 5px", borderRadius: 4, fontSize: 10.5 },
};
