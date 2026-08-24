import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ThetaForge",
  description: "Autonomous options trading agent — live paper-trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
