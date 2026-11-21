import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Veridocs — Document Verification Studio",
  description: "Fast, accurate document intelligence with citation verification.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
