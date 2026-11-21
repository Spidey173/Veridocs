"use client";

import ChatPanel from "../chat/ChatPanel";

export default function AIWorkspace() {
  return (
    <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] border-l border-[var(--border-subtle)] overflow-hidden">
      <ChatPanel />
    </div>
  );
}
