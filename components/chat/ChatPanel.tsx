"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { Send, Loader2, Bot, User, CornerDownLeft, Sparkles, Key, Check, X } from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { streamQuery, getUserApiKey, setUserApiKey, type CitationInfo, type CitationCheckResult } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import VerificationDrawer from "./VerificationDrawer";

export default function ChatPanel() {
  const [input, setInput] = useState("");
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [customKeyInput, setCustomKeyInput] = useState("");
  const [hasCustomKey, setHasCustomKey] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const k = getUserApiKey();
    setHasCustomKey(Boolean(k));
    if (k) setCustomKeyInput(k);
  }, []);

  const handleSaveKey = () => {
    setUserApiKey(customKeyInput);
    setHasCustomKey(Boolean(customKeyInput.trim()));
    setShowKeyModal(false);
  };

  const handleClearKey = () => {
    setUserApiKey("");
    setCustomKeyInput("");
    setHasCustomKey(false);
    setShowKeyModal(false);
  };

  const {
    sessionId,
    messages,
    suggestedQuestions,
    activeDocumentName,
    isQuerying,
    isBackendWaking,
    pendingQuestion,
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
    setPendingQuestion,
  } = useAppStore();

  useEffect(() => {
    if (pendingQuestion) {
      setInput(pendingQuestion);
      setPendingQuestion(null);
      inputRef.current?.focus();
    }
  }, [pendingQuestion, setPendingQuestion]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = useCallback(async () => {
    if (!input.trim() || !sessionId || isQuerying) return;

    const question = input.trim();
    setInput("");
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    const userMsgId = `user-${Date.now()}`;
    addMessage({
      id: userMsgId,
      role: "user",
      content: question,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    });

    const aiMsgId = `ai-${Date.now()}`;
    addMessage({
      id: aiMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    });

    setQuerying(true);
    setCurrentStreamingId(aiMsgId);

    try {
      const history = messages
        .filter((m) => !m.isStreaming)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const citations: CitationInfo[] = [];
      let citationCheck: CitationCheckResult | undefined = undefined;

      for await (const event of streamQuery(sessionId, question, history)) {
        switch (event.event) {
          case "token":
            appendToMessage(aiMsgId, (event.data?.text as string) || "");
            break;
          case "citation":
            citations.push(event.data as unknown as CitationInfo);
            break;
          case "citation_check":
            citationCheck = event.data as unknown as CitationCheckResult;
            break;
          case "error":
            appendToMessage(aiMsgId, `\n\n⚠️ Error: ${(event.data?.message as string) || "Unknown error"}`);
            break;
          case "done":
            updateMessage(aiMsgId, {
              isStreaming: false,
              citations,
              citation_check: citationCheck,
            });
            break;
        }
      }
    } catch (err: unknown) {
      const rawMsg = err instanceof Error ? err.message : "Failed to query document.";
      let userFriendlyMsg = `Error: ${rawMsg}`;
      if (rawMsg.includes("Failed to fetch") || rawMsg.includes("NetworkError")) {
        userFriendlyMsg = "⚠️ **Connection failed**: The backend on Render may still be spinning up from cold sleep (~20–30s). Please wait 15 seconds and try sending your question again.";
      }
      updateMessage(aiMsgId, {
        content: userFriendlyMsg,
        isStreaming: false,
      });
    } finally {
      setQuerying(false);
      setCurrentStreamingId(null);
    }
  }, [input, sessionId, isQuerying, messages, addMessage, appendToMessage, updateMessage, setQuerying, setCurrentStreamingId]);

  return (
    <div className="h-full flex flex-col bg-[var(--bg-surface)] text-[var(--text-primary)] select-none">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-xs text-[var(--text-muted)] space-y-4">
            <div className="w-10 h-10 rounded-full bg-[var(--color-accent-subtle)] text-[var(--color-accent)] flex items-center justify-center">
              <Bot className="w-5 h-5" />
            </div>
            <div className="max-w-sm space-y-1">
              <p className="font-semibold text-sm text-[var(--text-primary)]">
                Ask Questions Grounded in Document Text
              </p>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                Veridocs retrieves relevant chunks, streams answers with exact page citations, and verifies claim support.
              </p>
            </div>

            {/* Dynamic Contextual Question Prompts */}
            <div className="w-full max-w-sm space-y-1.5 pt-2 text-left">
              {((suggestedQuestions && suggestedQuestions.length > 0)
                ? suggestedQuestions
                : (activeDocumentName?.includes("sample_agreement"))
                  ? [
                      "What are the payment terms in this agreement?",
                      "What is the limitation of liability and uptime SLA?",
                      "What data protection and encryption standards are required?",
                    ]
                  : [
                      "Summarize this document",
                      "What are the key points?",
                      "What are the main requirements and dates?",
                    ]
              ).slice(0, 3).map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setInput(prompt)}
                  className="w-full p-2 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] text-xs text-[var(--text-primary)] transition-colors flex items-center gap-2"
                >
                  <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" />
                  <span className="truncate">{prompt}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col text-xs leading-relaxed ${
                m.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`max-w-[92%] rounded-lg p-3 ${
                  m.role === "user"
                    ? "bg-[var(--color-accent)] text-white"
                    : "bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--text-primary)]"
                }`}
              >
                <div className="flex items-center gap-1.5 mb-1 text-[10px] opacity-75 font-mono-data">
                  {m.role === "user" ? (
                    <>
                      <User className="w-3 h-3" />
                      <span>You</span>
                    </>
                  ) : (
                    <>
                      <Bot className="w-3 h-3 text-[var(--color-accent)]" />
                      <span>Veridocs AI</span>
                    </>
                  )}
                  <span>• {m.timestamp}</span>
                </div>

                {m.content ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none break-words text-xs">
                    <ReactMarkdown>{m.content}</ReactMarkdown>
                    {m.content.includes("No LLM is configured") && (
                      <div className="pt-2">
                        <button
                          type="button"
                          onClick={() => setShowKeyModal(true)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[var(--color-accent)] text-white text-xs font-semibold hover:bg-[var(--color-accent-hover)] transition-colors shadow-sm"
                        >
                          <Key className="w-3.5 h-3.5" />
                          <span>Enter Groq or OpenAI Key (Browser only)</span>
                        </button>
                      </div>
                    )}
                  </div>
                ) : m.isStreaming ? (
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] py-1">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
                    <span>Searching documents & generating answer...</span>
                  </div>
                ) : null}

                {/* Real Citation Check Drawer - only for real answers, never for system notices */}
                {m.role === "assistant" &&
                  !m.isStreaming &&
                  !m.content.startsWith("⚠️") &&
                  !m.content.includes("No LLM is configured") &&
                  !m.content.includes("Rate Limit Reached") && (
                    <VerificationDrawer
                      citations={m.citations}
                      citationCheck={m.citation_check}
                    />
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box Area */}
      <div className="p-3 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] space-y-2">
        {/* Backend Waking Notice */}
        {isBackendWaking && (
          <div className="flex items-center gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-500 text-[11px]">
            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
            <span>Backend is waking up on Render free-tier (~20–30s). Please wait...</span>
          </div>
        )}

        {/* Key Status & Rate Limit Indicator */}
        <div className="flex items-center justify-between px-0.5 text-[11px] text-[var(--text-muted)]">
          <span className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${hasCustomKey ? "bg-emerald-500" : "bg-amber-500"}`} />
            {hasCustomKey ? "Custom API key active (unlimited)" : "Public demo (20 queries/hr per IP)"}
          </span>
          <button
            type="button"
            onClick={() => setShowKeyModal(true)}
            className="hover:text-[var(--color-accent)] underline decoration-dotted transition-colors flex items-center gap-1"
          >
            <Key className="w-3 h-3" />
            {hasCustomKey ? "Edit Key" : "Add Key (Bypass limits)"}
          </button>
        </div>

        {/* Custom Key Modal */}
        {showKeyModal && (
          <div className="p-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] space-y-2 text-xs shadow-md">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-[var(--text-primary)] flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-[var(--color-accent)]" /> Bring Your Own API Key
              </span>
              <button
                type="button"
                onClick={() => setShowKeyModal(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-[11px] text-[var(--text-secondary)] leading-tight">
              Paste an OpenAI or Groq key (<code className="bg-[var(--bg-canvas)] px-1 py-0.5 rounded">sk-...</code> / <code className="bg-[var(--bg-canvas)] px-1 py-0.5 rounded">gsk_...</code>). Stored locally in your browser only. Never saved to server disk or logs.
            </p>
            <input
              type="password"
              value={customKeyInput}
              onChange={(e) => setCustomKeyInput(e.target.value)}
              placeholder="Paste sk-... or gsk_... key"
              className="w-full p-2 text-xs rounded border border-[var(--border-default)] bg-[var(--bg-canvas)] text-[var(--text-primary)] outline-none focus:border-[var(--color-accent)]"
            />
            <div className="flex items-center justify-end gap-2 pt-1">
              {hasCustomKey && (
                <button
                  type="button"
                  onClick={handleClearKey}
                  className="px-2.5 py-1 text-[11px] rounded border border-[var(--border-default)] hover:bg-[var(--bg-surface)] text-[var(--color-error)]"
                >
                  Clear Key
                </button>
              )}
              <button
                type="button"
                onClick={handleSaveKey}
                className="px-3 py-1 text-[11px] rounded bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] font-medium flex items-center gap-1"
              >
                <Check className="w-3 h-3" /> Save
              </button>
            </div>
          </div>
        )}

        <div className="relative border border-[var(--border-default)] rounded-lg focus-within:border-[var(--color-accent)] bg-[var(--bg-canvas)] transition-colors">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={!sessionId || isQuerying || isBackendWaking}
            placeholder={
              isBackendWaking
                ? "Connecting to backend... please wait"
                : sessionId
                ? "Ask a question about the document... (Enter to send)"
                : "Upload a document to start asking questions..."
            }
            className="w-full p-2.5 pr-10 text-xs bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-none outline-none max-h-32 disabled:opacity-50"
          />

          <button
            type="button"
            disabled={!input.trim() || !sessionId || isQuerying || isBackendWaking}
            onClick={handleSubmit}
            className="absolute right-2 bottom-2 p-1.5 rounded bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-30 disabled:hover:bg-[var(--color-accent)]"
            title="Send question"
          >
            {isQuerying ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CornerDownLeft className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
