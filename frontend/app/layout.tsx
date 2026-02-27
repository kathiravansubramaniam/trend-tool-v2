import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trend Analysis Bot",
  description: "Ask questions across 130+ trend reports",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
