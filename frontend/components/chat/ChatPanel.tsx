"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import {
  Send,
  Loader2,
  Bot,
  User,
  FileText,
  CornerDownLeft,
  Search,
} from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import {
  streamQuery,
  type CitationInfo,
  type ClaimVerificationItem,
  type RagTriadMetrics,
} from "@/lib/api";
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
    insights,
    selectedFileNames,
    pendingQuestion,
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
    setPendingQuestion,
    highlightCitation,
  } = useAppStore();

  // Watch for pending question dispatched from left sidebar or suggestions
  useEffect(() => {
    if (pendingQuestion) {
      setInput(pendingQuestion);
      setPendingQuestion(null);
      inputRef.current?.focus();
    }
  }, [pendingQuestion, setPendingQuestion]);

  // Auto-scroll to bottom on message updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Global Keyboard shortcuts: Cmd+K to focus input, J / K to cycle citations
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Cmd+K or Ctrl+K: Focus ask input
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        return;
      }

      // 2. J / K citation cycling (only when not actively typing in an input/textarea)
      const isInputActive =
        document.activeElement?.tagName === "INPUT" ||
        document.activeElement?.tagName === "TEXTAREA";

      if (!isInputActive && (e.key === "j" || e.key === "k" || e.key === "J" || e.key === "K")) {
        // Collect all citations from the latest assistant message
        const lastAssistant = [...messages].reverse().find(
          (m) => m.role === "assistant" && m.citations && m.citations.length > 0
        );
        if (!lastAssistant || !lastAssistant.citations || lastAssistant.citations.length === 0) return;

        const cits = lastAssistant.citations;
        const currentHighlight = useAppStore.getState().highlightedCitation;
        let nextIdx = 0;

        if (currentHighlight) {
          const currentIdx = cits.findIndex(
            (c) =>
              c.page === currentHighlight.page &&
              c.highlighted_text === currentHighlight.highlighted_text
          );
          if (e.key.toLowerCase() === "j") {
            // Next citation
            nextIdx = (currentIdx + 1) % cits.length;
          } else {
            // Previous citation
            nextIdx = (currentIdx - 1 + cits.length) % cits.length;
          }
        }

        e.preventDefault();
        highlightCitation(cits[nextIdx]);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [messages, highlightCitation]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
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
      timestamp: new Date(),
    });

    const aiMsgId = `ai-${Date.now()}`;
    addMessage({
      id: aiMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date(),
    });

    setQuerying(true);
    setCurrentStreamingId(aiMsgId);

    try {
      const history = messages
        .filter((m) => !m.isStreaming)
        .slice(-6)
        .map((m) => ({
          role: m.role,
          content: m.content,
        }));

      const citations: CitationInfo[] = [];
      let confidence = 0;
      let verifiedCount = 0;
      let inferredCount = 0;
      let hallucinatedCount = 0;
      let claimVerifications: ClaimVerificationItem[] = [];
      let ragTriad: RagTriadMetrics | undefined = undefined;

      for await (const event of streamQuery(sessionId, question, history, selectedFileNames)) {
        switch (event.event) {
          case "token":
            appendToMessage(aiMsgId, event.data.text as string);
            break;
          case "citation":
            citations.push(event.data as unknown as CitationInfo);
            break;
          case "confidence":
            confidence = event.data.score as number;
            verifiedCount = (event.data.verified_claims as number) || 0;
            inferredCount = (event.data.inferred_claims as number) || 0;
            hallucinatedCount = (event.data.hallucinated_claims as number) || 0;
            break;
          case "verification":
            claimVerifications =
              (event.data.claim_details as unknown as ClaimVerificationItem[]) || [];
            break;
          case "audit_metrics":
            ragTriad = event.data as unknown as RagTriadMetrics;
            break;
          case "done":
            updateMessage(aiMsgId, {
              isStreaming: false,
              citations,
              confidence_score: confidence,
              claim_verifications: claimVerifications,
              verified_claims: verifiedCount,
              inferred_claims: inferredCount,
              hallucinated_claims: hallucinatedCount,
              rag_triad: ragTriad,
            });
            break;
          case "error": {
            const rawMsg = (event.data?.message as string) || "";
            updateMessage(aiMsgId, {
              content:
                rawMsg ||
                "An error occurred while evaluating this query against the document corpus.",
              isStreaming: false,
            });
            break;
          }
        }
      }
    } catch (err) {
      const errStr = err instanceof Error ? err.message : "Failed to generate answer";
      updateMessage(aiMsgId, {
        content: `Query error: ${errStr}. Please verify that the engine is reachable.`,
        isStreaming: false,
      });
    } finally {
      setQuerying(false);
      setCurrentStreamingId(null);
    }
  }, [
    input,
    sessionId,
    isQuerying,
    messages,
    selectedFileNames,
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSuggestedQuestion = (question: string) => {
    setInput(question);
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-full bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <EmptyState
            suggestedQuestions={insights?.suggested_questions || []}
            onQuestionClick={handleSuggestedQuestion}
          />
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
              />
            ))}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Follow-Ups (Quiet, Inline) */}
      {messages.length > 0 && !isQuerying && (
        <SuggestedFollowups
          messages={messages}
          onClick={handleSuggestedQuestion}
        />
      )}

      {/* Input Area: Dense, Sharp, Visible Focus Ring */}
      <div className="p-3 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0">
        <div className="flex items-end gap-2 p-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-canvas)] focus-within:border-[var(--color-accent)] focus-within:ring-1 focus-within:ring-[var(--color-accent)] transition-all">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question or cite a clause... (⌘K)"
            className="flex-1 bg-transparent text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-none focus:outline-none py-1.5 px-2 max-h-[120px] leading-relaxed"
            rows={1}
            disabled={isQuerying}
            id="chat-input"
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!input.trim() || isQuerying}
            className={`
              p-1.5 rounded text-xs transition-colors shrink-0
              ${
                input.trim() && !isQuerying
                  ? "bg-[var(--color-accent)] text-white hover:opacity-90"
                  : "bg-[var(--bg-subtle)] text-[var(--text-muted)] cursor-not-allowed"
              }
            `}
            id="send-button"
            title="Submit query (Enter)"
          >
            {isQuerying ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CornerDownLeft className="w-3.5 h-3.5" />
            )}
          </button>
        </div>

        <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] font-mono-data mt-1.5 px-1">
          <span>Grounding active • Page coordinate bounding boxes</span>
          <span className="hidden sm:inline">Press J / K to step through citations</span>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const { highlightCitation, setCurrentPage } = useAppStore();
  const [hoveredCitation, setHoveredCitation] = useState<CitationInfo | null>(null);

  // Parse citations mapping
  const citations = message.citations || [];

  // Helper to resolve citation index
  const getCitationByIndex = (idx: number): CitationInfo | undefined => {
    return citations[idx - 1] || citations[0];
  };

  // Convert inline citations like [1] or [Page 1] into interactive numbered chips
  const processedContent = message.content
    ? message.content
        // Convert [1], [2], etc. into custom markdown links [#cite-1]
        .replace(/\[(\d+)\](?!\()/g, "[$1](#cite-$1)")
        // Convert [Page 1] into custom markdown links [#page-1]
        .replace(/\[Page\s*(\d+)\](?!\()/gi, "[$&](#page-$1)")
    : "";

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div className="flex items-center gap-1.5 mb-1 px-1 text-[10px] font-mono-data text-[var(--text-muted)]">
        {isUser ? (
          <span>Inquiry</span>
        ) : (
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" />
            <span>Veridocs Assistant</span>
          </span>
        )}
      </div>

      <div
        className={`
          max-w-[94%] rounded-lg px-3.5 py-3 text-xs border
          ${
            isUser
              ? "bg-[var(--bg-surface-raised)] border-[var(--border-default)] text-[var(--text-primary)]"
              : "bg-[var(--bg-surface)] border-[var(--border-subtle)] text-[var(--text-primary)]"
          }
        `}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed text-[13px]">{message.content}</p>
        ) : (
          <>
            {message.content ? (
              <div className="markdown-content relative">
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => {
                      // 1. Numbered Citation Chips: e.g. [1], [2]
                      if (href?.startsWith("#cite-")) {
                        const citeNum = parseInt(href.replace("#cite-", ""), 10);
                        const matchedCit = getCitationByIndex(citeNum);

                        return (
                          <span className="relative inline-block mx-0.5">
                            <button
                              type="button"
                              onClick={() => {
                                if (matchedCit) {
                                  highlightCitation(matchedCit);
                                }
                              }}
                              onMouseEnter={() => {
                                if (matchedCit) setHoveredCitation(matchedCit);
                              }}
                              onMouseLeave={() => setHoveredCitation(null)}
                              className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded text-[10px] font-mono-data font-semibold bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)] hover:bg-[var(--color-accent)] hover:text-white transition-colors cursor-pointer align-baseline"
                              title={`Jump to Page ${matchedCit?.page || 1}`}
                            >
                              [{children}]
                            </button>

                            {/* Source snippet popover on hover */}
                            {hoveredCitation === matchedCit && matchedCit && (
                              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2 rounded border border-[var(--border-default)] bg-[var(--bg-surface-raised)] text-[11px] text-[var(--text-secondary)] shadow-xl z-50 pointer-events-none block">
                                <span className="flex items-center justify-between text-[9px] font-mono-data text-[var(--text-muted)] uppercase mb-1 border-b border-[var(--border-subtle)] pb-0.5">
                                  <span className="truncate max-w-[140px] font-semibold text-[var(--text-primary)]">
                                    {matchedCit.source_file}
                                  </span>
                                  <span>Page {matchedCit.page}</span>
                                </span>
                                <span className="line-clamp-3 italic text-[var(--text-primary)] leading-relaxed">
                                  &quot;{matchedCit.highlighted_text}&quot;
                                </span>
                              </span>
                            )}
                          </span>
                        );
                      }

                      // 2. Page links: e.g. [Page 1]
                      if (href?.startsWith("#page-")) {
                        const pageNum = parseInt(href.replace("#page-", ""), 10);
                        const matchedCit = citations.find((c) => c.page === pageNum) || {
                          citation_id: 1,
                          page: pageNum,
                          source_file: "",
                          highlighted_text: "",
                        };

                        return (
                          <button
                            type="button"
                            onClick={() => {
                              setCurrentPage(pageNum);
                              if (matchedCit.highlighted_text) {
                                highlightCitation(matchedCit);
                              }
                            }}
                            className="inline-flex items-center gap-1 px-1.5 py-0.2 mx-0.5 rounded text-[10px] font-mono-data font-medium bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)] hover:bg-[var(--color-accent)] hover:text-white transition-colors align-baseline"
                          >
                            <FileText className="w-2.5 h-2.5" />
                            {children}
                          </button>
                        );
                      }

                      return (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[var(--color-accent)] underline hover:opacity-80"
                        >
                          {children}
                        </a>
                      );
                    },
                    h1: ({ children }) => (
                      <h1 className="text-sm font-serif-doc font-semibold mt-2 mb-1 text-[var(--text-primary)]">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-xs font-serif-doc font-semibold mt-2 mb-1 text-[var(--text-primary)]">
                        {children}
                      </h2>
                    ),
                    ul: ({ children }) => (
                      <ul className="space-y-1 my-1.5 pl-4 list-disc marker:text-[var(--color-accent)]">
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="space-y-1 my-1.5 pl-4 list-decimal marker:text-[var(--color-accent)]">
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li className="leading-relaxed text-[12.5px] text-[var(--text-primary)]">
                        {children}
                      </li>
                    ),
                    p: ({ children }) => (
                      <p className="mb-2 last:mb-0 leading-relaxed text-[12.5px] text-[var(--text-primary)]">
                        {children}
                      </p>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-2 rounded border border-[var(--border-subtle)]">
                        <table className="w-full text-left text-xs border-collapse">
                          {children}
                        </table>
                      </div>
                    ),
                  }}
                >
                  {processedContent}
                </ReactMarkdown>
              </div>
            ) : message.isStreaming ? (
              <div className="flex items-center gap-2 py-1 text-xs text-[var(--text-muted)] font-mono-data">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
                <span>Evaluating retrieved clauses...</span>
              </div>
            ) : null}

            {/* Verification Drawer: Compact, Honest Telemetry */}
            {((citations && citations.length > 0) ||
              (message.claim_verifications && message.claim_verifications.length > 0) ||
              message.rag_triad) &&
              !message.isStreaming && (
                <VerificationDrawer
                  citations={citations}
                  confidenceScore={message.confidence_score}
                  claimVerifications={message.claim_verifications}
                  ragTriad={message.rag_triad}
                />
              )}
          </>
        )}
      </div>
    </div>
  );
}

function EmptyState({
  suggestedQuestions,
  onQuestionClick,
}: {
  suggestedQuestions: string[];
  onQuestionClick: (q: string) => void;
}) {
  const displayQuestions =
    suggestedQuestions && suggestedQuestions.length > 0
      ? suggestedQuestions.slice(0, 4)
      : [
          "Summarize the primary covenants and obligations",
          "Identify payment terms, interest rates, and invoice windows",
          "What are the limitation of liability caps and damages exclusions?",
          "Extract termination rights, cure periods, and notice schedules",
        ];

  return (
    <div className="h-full flex flex-col justify-center py-6 px-2 space-y-4">
      <div className="border border-[var(--border-subtle)] rounded-lg p-4 bg-[var(--bg-surface)]">
        <h3 className="text-xs font-serif-doc font-semibold text-[var(--text-primary)] mb-1">
          Document Intelligence Assistant
        </h3>
        <p className="text-[11.5px] text-[var(--text-muted)] leading-relaxed">
          Ask specific legal, financial, or technical questions against the loaded document corpus. Every claim is corroborated with coordinate-level source citations.
        </p>
      </div>

      <div className="space-y-1.5">
        <p className="text-[10px] font-mono-data text-[var(--text-muted)] uppercase tracking-wider px-1">
          Suggested Inquiries
        </p>
        {displayQuestions.map((q, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onQuestionClick(q)}
            className="w-full text-left p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-raised)] hover:border-[var(--border-strong)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-start gap-2 group"
          >
            <span className="text-[var(--color-accent)] font-mono-data font-bold mt-0.5">
              ›
            </span>
            <span className="line-clamp-2 leading-relaxed">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SuggestedFollowups({
  messages,
  onClick,
}: {
  messages: ChatMessage[];
  onClick: (q: string) => void;
}) {
  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && !m.isStreaming);

  const suggestions = [
    "What are the liability caps?",
    "Compare payment terms with baseline",
    "Are there SLA penalties or downtime credits?",
  ];

  if (!lastAssistant || lastAssistant.content.length < 30) return null;

  return (
    <div className="px-3 py-1.5 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] flex gap-1.5 overflow-x-auto shrink-0">
      {suggestions.map((s, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onClick(s)}
          className="shrink-0 px-2.5 py-1 rounded text-[11px] font-mono-data text-[var(--text-secondary)] border border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] transition-colors"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
