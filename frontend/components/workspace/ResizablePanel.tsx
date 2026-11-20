"use client";

import { useEffect, useRef, useState } from "react";

interface ResizablePanelProps {
  width: number;
  minWidth: number;
  maxWidth?: number;
  direction: "left" | "right";
  onWidthChange: (width: number) => void;
  isCollapsed: boolean;
  children: React.ReactNode;
}

export default function ResizablePanel({
  width,
  minWidth,
  maxWidth = 700,
  direction,
  onWidthChange,
  isCollapsed,
  children,
}: ResizablePanelProps) {
  const resizeRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;

      let newWidth = width;
      if (direction === "left") {
        newWidth = e.clientX;
      } else {
        newWidth = window.innerWidth - e.clientX;
      }

      if (newWidth >= minWidth && newWidth <= maxWidth) {
        onWidthChange(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.style.cursor = "default";
      document.body.classList.remove("select-none");
    };

    if (isResizing) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing, width, minWidth, maxWidth, direction, onWidthChange]);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    document.body.style.cursor = "col-resize";
    document.body.classList.add("select-none");
  };

  return (
    <div
      className="relative flex h-full shrink-0"
      style={{
        width: isCollapsed ? (direction === "left" ? "48px" : "0px") : `${width}px`,
        transition: isResizing ? "none" : "width 180ms cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <div className="w-full h-full overflow-hidden flex flex-col bg-[var(--bg-surface)]">
        {children}
      </div>

      {/* Resize Handle: 1px divider, subtle orange on hover/active */}
      {!isCollapsed && (
        <div
          ref={resizeRef}
          onMouseDown={handleMouseDown}
          className={`
            absolute top-0 bottom-0 w-2 cursor-col-resize z-50 group
            ${direction === "left" ? "right-0 translate-x-1/2" : "left-0 -translate-x-1/2"}
          `}
          title="Drag to resize panel"
        >
          <div className="w-[1px] h-full bg-[var(--border-subtle)] mx-auto group-hover:bg-[var(--color-accent)] group-hover:w-[2px] transition-all" />
        </div>
      )}
    </div>
  );
}
