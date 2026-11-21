"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { Send, Loader2, Bot, User, CornerDownLeft, Sparkles } from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { streamQuery, type CitationInfo, type CitationCheckResult } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import VerificationDrawer from "./VerificationDrawer";

export default function ChatPanel() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    sessionId,
    messages,
    isQuerying,
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
      const msg = err instanceof Error ? err.message : "Failed to query document.";
      updateMessage(aiMsgId, {
        content: `Error: ${msg}`,
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

            {/* Quick Question Prompts */}
            <div className="w-full max-w-sm space-y-1.5 pt-2 text-left">
              <button
                type="button"
                onClick={() => setInput("What are the payment terms in this agreement?")}
                className="w-full p-2 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] text-xs text-[var(--text-primary)] transition-colors flex items-center gap-2"
              >
                <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" />
                <span className="truncate">What are the payment terms in this agreement?</span>
              </button>
              <button
                type="button"
                onClick={() => setInput("What is the limitation of liability and uptime SLA?")}
                className="w-full p-2 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] text-xs text-[var(--text-primary)] transition-colors flex items-center gap-2"
              >
                <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" />
                <span className="truncate">What is the limitation of liability and uptime SLA?</span>
              </button>
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
                  </div>
                ) : m.isStreaming ? (
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] py-1">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
                    <span>Searching documents & generating answer...</span>
                  </div>
                ) : null}

                {/* Real Citation Check Drawer */}
                {m.role === "assistant" && !m.isStreaming && (
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

      {/* Input Box */}
      <div className="p-3 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="relative border border-[var(--border-default)] rounded-lg focus-within:border-[var(--color-accent)] bg-[var(--bg-canvas)] transition-colors">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={!sessionId || isQuerying}
            placeholder={
              sessionId
                ? "Ask a question about the document... (Enter to send)"
                : "Upload a document to start asking questions..."
            }
            className="w-full p-2.5 pr-10 text-xs bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-none outline-none max-h-32 disabled:opacity-50"
          />

          <button
            type="button"
            disabled={!input.trim() || !sessionId || isQuerying}
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
