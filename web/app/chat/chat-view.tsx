"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/types";
import { askChat } from "@/lib/api";
import { GlossaryText } from "@/lib/glossary";

const SUGGESTIONS = [
  "ตอนนี้ตัวไหนน่าห่วงสุด?",
  "สรุปภาพรวม watchlist หน่อย",
  "พอร์ตตอนนี้ชนะ VT ไหม?",
];

export default function ChatView() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setError(null);
    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const answer = await askChat(q, history);
      setMessages((prev) => [...prev, { role: "assistant", text: answer.conclusion, steps: answer.steps }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat-wrap">
      {messages.length === 0 && (
        <div className="chat-suggestions">
          <span className="muted-sm">ลองถามดู:</span>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip-btn" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="chat-log">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            <div className="chat-bubble">
              {m.role === "assistant" ? <GlossaryText text={m.text} /> : m.text}
            </div>
            {m.steps && m.steps.length > 0 && (
              <details className="chat-trace">
                <summary>🔧 ดูว่าไปดึงข้อมูลอะไรมา ({m.steps.length} ขั้น)</summary>
                <ol className="inv-steps">
                  {m.steps.map((s, j) => (
                    <li key={j}>
                      <div className="inv-tool">
                        🔧 <code>{s.tool}</code>
                        {Object.keys(s.args).length > 0 && (
                          <span className="inv-args">({Object.values(s.args).join(", ")})</span>
                        )}
                      </div>
                      <div className="inv-obs">{s.observation}</div>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        ))}
        {busy && (
          <div className="chat-msg chat-assistant">
            <div className="chat-bubble chat-thinking">กำลังคิด…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <div className="notice">{error}</div>}

      <form
        className="chat-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="input"
          placeholder="ถามอะไรก็ได้เกี่ยวกับพอร์ต/watchlist…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button className="btn" type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "ถาม"}
        </button>
      </form>
    </div>
  );
}