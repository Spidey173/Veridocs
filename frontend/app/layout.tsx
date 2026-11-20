import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Inter, JetBrains_Mono, Lora } from "next/font/google";
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

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Veridocs — Contract & Document Verification Studio",
  description:
    "Dense, forensic document intelligence workspace with coordinate-grounded citations, clause diffs, and contradiction matrix.",
  keywords: [
    "document analysis",
    "contract review",
    "grounded QA",
    "PDF verification",
    "citations",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`dark ${plusJakartaSans.variable} ${inter.variable} ${lora.variable} ${jetbrainsMono.variable}`}
    >
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
