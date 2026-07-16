// AI Chat — ChatGPT-style interface for network engineers
import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, Bot, User, Loader } from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

const SUGGESTED = [
  "Which devices are currently down?",
  "What's the current network health?",
  "Are there any cascading failures?",
  "What's wrong with R1?",
  "Which alerts need immediate attention?",
];

function Message({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'flex-start',
      flexDirection: isUser ? 'row-reverse' : 'row',
      animation: 'fadeInUp 0.2s ease',
      marginBottom: 16,
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        background: isUser ? 'var(--accent-blue)' : 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isUser ? <User size={16} color="white" /> : <Bot size={16} color="white" />}
      </div>
      <div style={{
        maxWidth: '72%', padding: '12px 16px',
        background: isUser ? 'var(--accent-blue)' : 'var(--bg-card)',
        border: isUser ? 'none' : '1px solid var(--border)',
        borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
        fontSize: 14, lineHeight: 1.6,
        color: isUser ? 'white' : 'var(--text-primary)',
        whiteSpace: 'pre-wrap',
      }}>
        {msg.content}
      </div>
    </div>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '👋 Hi! I\'m Marvis, your AI network assistant.\n\nI can help you:\n• Diagnose network issues in plain English\n• Check device health and alerts\n• Explain root causes of incidents\n• Recommend immediate actions\n\nWhat would you like to know about your network?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const sendMessage = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput('');

    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await axios.post(`${API}/chat`, {
        session_id: sessionId,
        message: msg,
      });
      setSessionId(res.data.session_id);
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: '❌ Sorry, I couldn\'t connect to the AI service. Is the API Gateway running?' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 48px)', animation: 'fadeInUp 0.3s ease' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>AI Network Assistant</h1>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Powered by Groq LLaMA 3 70B · Ask anything about your network</div>
      </div>

      {/* Suggested prompts (show only at start) */}
      {messages.length === 1 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
          {SUGGESTED.map(s => (
            <button key={s} className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => sendMessage(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4, marginBottom: 16 }}>
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        {loading && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-blue))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={16} color="white" />
            </div>
            <div style={{ padding: '12px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '4px 16px 16px 16px' }}>
              <Loader size={16} style={{ animation: 'spin 1s linear infinite' }} color="var(--accent-blue)" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10, padding: '16px 0 0', borderTop: '1px solid var(--border)' }}>
        <textarea
          className="input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about your network... (Enter to send, Shift+Enter for new line)"
          rows={2}
          style={{ resize: 'none', lineHeight: 1.5 }}
          disabled={loading}
        />
        <button
          className="btn btn-primary"
          onClick={() => sendMessage()}
          disabled={!input.trim() || loading}
          style={{ flexShrink: 0, alignSelf: 'flex-end', height: 42 }}
        >
          <Send size={16} />
        </button>
      </div>

      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  );
}
