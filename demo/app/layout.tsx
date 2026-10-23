import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Veridocs — Forensic Document Intelligence & Visual Grounding",
  description:
    "Interactive portfolio demo for Veridocs: Smart QA with physical canvas word highlighting, side-by-side contract contradiction auditing, and 3-state sentence claim verification.",
  metadataBase: new URL("https://veridocs17.vercel.app"),
  openGraph: {
    title: "Veridocs — Forensic Document QA & Grounding Engine",
    description: "Physical visual document highlighting & side-by-side contract contradiction matrix.",
    url: "https://veridocs17.vercel.app",
    siteName: "Veridocs Demo",
    locale: "en_US",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-midnight-950 text-text-primary antialiased selection:bg-amber-500/30 selection:text-white">
        {children}
      </body>
    </html>
  );
}
