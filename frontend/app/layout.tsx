import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Veridocs — Intelligent Document Analysis",
  description:
    "Enterprise-grade AI document intelligence platform. Upload PDFs, get instant answers with source citations, executive summaries, and deep analysis powered by advanced RAG technology.",
  keywords: [
    "AI",
    "document analysis",
    "PDF",
    "RAG",
    "enterprise",
    "intelligence",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-midnight-950 text-text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
