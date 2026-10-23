import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-plus-jakarta",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Veridocs — Forensic Document Intelligence & Grounding Engine",
  description:
    "Enterprise-grade AI document intelligence platform. Forensic cross-document contradiction auditing, pixel-level canvas visual grounding, and sub-second hybrid retrieval.",
  keywords: [
    "AI",
    "document analysis",
    "contradiction engine",
    "PDF visual grounding",
    "RAG",
    "forensics",
    "intelligence",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`dark ${plusJakartaSans.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-midnight-950 text-text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
