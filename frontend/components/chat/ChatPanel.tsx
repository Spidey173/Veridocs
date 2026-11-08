"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  MessageSquare,
  FileText,
} from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { streamQuery, type CitationInfo, type ClaimVerificationItem, type RagTriadMetrics } from "@/lib/api";
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
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
  } = useAppStore();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

    // Add user message
    const userMsgId = `user-${Date.now()}`;
    addMessage({
      id: userMsgId,
      role: "user",
      content: question,
      timestamp: new Date(),
    });

    // Add placeholder AI message
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
      // Build history from previous messages
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
            claimVerifications = (event.data.claim_details as unknown as ClaimVerificationItem[]) || [];
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
              content: rawMsg || "Sorry, an error occurred while generating the response. Please try again.",
              isStreaming: false,
            });
            break;
          }
        }
      }
    } catch (err) {
      const errStr = err instanceof Error ? err.message : "Failed to get response";
      updateMessage(aiMsgId, {
        content: `Error: ${errStr}`,
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
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 ? (
          <EmptyState
            suggestedQuestions={insights?.suggested_questions || []}
            onQuestionClick={handleSuggestedQuestion}
          />
        ) : (
          <>
            {messages.map((msg, idx) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                animationDelay={idx * 0.02}
              />
            ))}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested follow-ups */}
      {messages.length > 0 && !isQuerying && (
        <SuggestedFollowups
          messages={messages}
          onClick={handleSuggestedQuestion}
        />
      )}

      {/* Input Area */}
      <div className="px-4 py-3 border-t border-white/6">
        <div className="flex items-end gap-2 p-2 rounded-xl glass-elevated">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your documents..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted resize-none focus:outline-none py-1.5 px-2 max-h-[120px]"
            rows={1}
            disabled={isQuerying}
            id="chat-input"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || isQuerying}
            className={`
              p-2 rounded-lg transition-all duration-200
              ${
                input.trim() && !isQuerying
                  ? "bg-accent-primary text-midnight-950 hover:bg-accent-secondary"
                  : "bg-white/5 text-text-muted cursor-not-allowed"
              }
            `}
            id="send-button"
          >
            {isQuerying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>

        <p className="text-[10px] text-text-muted text-center mt-2 opacity-60">
          Veridocs may make mistakes. Verify important information with the source document.
        </p>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  animationDelay = 0,
}: {
  message: ChatMessage;
  animationDelay?: number;
}) {
  const isUser = message.role === "user";
  const { setCurrentPage } = useAppStore();

  // Convert inline citations like [Page 1] into clickable anchor links [#page-1]
  const processedContent = message.content
    ? message.content.replace(/\[Page\s*(\d+)\](?!\()/gi, "[$&](#page-$1)")
    : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay, duration: 0.3 }}
      className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="shrink-0 w-8 h-8 rounded-xl bg-accent-primary/15 border border-accent-primary/25 flex items-center justify-center mt-0.5 shadow-sm">
          <Bot className="w-4 h-4 text-accent-primary" />
        </div>
      )}

      <div
        className={`
          max-w-[88%] rounded-2xl px-5 py-4 shadow-sm
          ${
            isUser
              ? "bg-accent-primary text-midnight-950 font-semibold rounded-br-md"
              : "glass border border-white/10 rounded-bl-md bg-white/[0.03]"
          }
        `}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {message.content ? (
              <div className="text-sm markdown-content">
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => {
                      if (href?.startsWith("#page-")) {
                        const pageNum = parseInt(href.replace("#page-", ""), 10);
                        return (
                          <button
                            type="button"
                            onClick={() => setCurrentPage(pageNum)}
                            title={`Jump to Page ${pageNum} in viewer`}
                            className="inline-flex items-center px-1.5 py-0.5 mx-1 rounded text-xs font-mono font-medium bg-accent-primary/15 text-accent-primary border border-accent-primary/30 hover:bg-accent-primary/25 hover:border-accent-primary/50 cursor-pointer transition-all shadow-sm align-baseline"
                          >
                            <FileText className="w-3 h-3 mr-1 inline opacity-85" />
                            {children}
                          </button>
                        );
                      }
                      return (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-primary underline hover:text-accent-primary/80 transition-colors"
                        >
                          {children}
                        </a>
                      );
                    },
                    h1: ({ children }) => (
                      <h1 className="text-base font-bold text-text-primary mt-3 mb-1.5 first:mt-0 tracking-tight flex items-center gap-1.5">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-sm font-semibold text-text-primary mt-3 mb-1 first:mt-0">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-sm font-semibold text-accent-primary mt-3 mb-1 first:mt-0">
                        {children}
                      </h3>
                    ),
                    ul: ({ children }) => (
                      <ul className="space-y-1.5 my-2 pl-4 list-disc marker:text-accent-primary/80">
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="space-y-1.5 my-2 pl-4 list-decimal marker:text-accent-primary/80">
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li className="text-text-secondary leading-relaxed pl-1 text-[13.5px]">
                        {children}
                      </li>
                    ),
                    p: ({ children }) => (
                      <p className="mb-2.5 last:mb-0 leading-relaxed text-text-secondary text-[13.5px]">
                        {children}
                      </p>
                    ),
                    strong: ({ children }) => (
                      <strong className="font-semibold text-text-primary">{children}</strong>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-3 rounded-lg border border-white/10 bg-white/[0.02]">
                        <table className="w-full text-left text-xs border-collapse">{children}</table>
                      </div>
                    ),
                    thead: ({ children }) => (
                      <thead className="bg-white/5 border-b border-white/10 text-text-primary">
                        {children}
                      </thead>
                    ),
                    th: ({ children }) => <th className="p-2.5 font-semibold text-text-primary">{children}</th>,
                    td: ({ children }) => <td className="p-2.5 border-b border-white/5 text-text-secondary">{children}</td>,
                    code: ({ children }) => (
                      <code className="px-1.5 py-0.5 rounded text-xs font-mono bg-white/10 text-accent-primary font-medium">
                        {children}
                      </code>
                    ),
                  }}
                >
                  {processedContent}
                </ReactMarkdown>
              </div>
            ) : message.isStreaming ? (
              <div className="flex items-center gap-2 py-1">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:300ms]" />
                </div>
                <span className="text-xs text-text-muted">Thinking...</span>
              </div>
            ) : null}

            {/* Streaming cursor */}
            {message.isStreaming && message.content && (
              <span className="inline-block w-0.5 h-4 bg-accent-primary animate-pulse ml-0.5 align-middle" />
            )}

            {/* Verification & RAG Triad Drawer */}
            {((message.citations && message.citations.length > 0) || (message.claim_verifications && message.claim_verifications.length > 0) || message.rag_triad) && !message.isStreaming && (
              <VerificationDrawer
                citations={message.citations || []}
                confidenceScore={message.confidence_score}
                claimVerifications={message.claim_verifications}
                ragTriad={message.rag_triad}
              />
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="shrink-0 w-8 h-8 rounded-xl bg-white/10 border border-white/10 flex items-center justify-center mt-0.5 shadow-sm">
          <User className="w-4 h-4 text-text-secondary" />
        </div>
      )}
    </motion.div>
  );
}

function EmptyState({
  suggestedQuestions,
  onQuestionClick,
}: {
  suggestedQuestions: string[];
  onQuestionClick: (q: string) => void;
}) {
  const displayQuestions = suggestedQuestions && suggestedQuestions.length > 0
    ? suggestedQuestions.slice(0, 4)
    : [
        "Summarize this document",
        "Compare the key findings",
        "Extract the primary risks",
        "Generate a project timeline",
      ];

  return (
    <div className="flex flex-col items-center justify-center h-full py-8 px-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-accent-primary/10 flex items-center justify-center mx-auto mb-4">
          <Sparkles className="w-7 h-7 text-accent-primary" />
        </div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">
          Ask anything
        </h3>
        <p className="text-sm text-text-muted mb-6 max-w-xs">
          Ask any question about your uploaded documents. I&apos;ll find the answer with source citations.
        </p>
      </motion.div>

      <div className="w-full max-w-md space-y-2">
        <p className="text-xs text-text-muted font-medium uppercase tracking-wider mb-2 text-center">
          Suggested Queries
        </p>
        {displayQuestions.map((q, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.05 }}
            onClick={() => onQuestionClick(q)}
            className="w-full text-left p-3 rounded-xl glass hover:glass-active
              text-sm text-text-secondary hover:text-text-primary
              transition-all duration-200 group flex items-center gap-2"
          >
            <MessageSquare className="w-3.5 h-3.5 text-text-muted group-hover:text-accent-primary shrink-0 transition-colors" />
            <span className="line-clamp-2">{q}</span>
          </motion.button>
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

  // Dynamic follow-up suggestions based on context
  const suggestions = [
    "What are the main technologies used?",
    "Can you summarize the primary experience?",
    "What key achievements are mentioned?",
  ];

  if (!lastAssistant || lastAssistant.content.length < 30) return null;

  return (
    <div className="px-4 py-2 flex gap-2 overflow-x-auto">
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onClick(s)}
          className="shrink-0 px-3 py-1.5 rounded-full text-xs text-text-muted
            border border-white/8 hover:border-accent-primary/30 hover:text-accent-secondary
            hover:bg-accent-primary/5 transition-all duration-200"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
