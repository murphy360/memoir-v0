import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Memoir MVP",
  description: "Voice-first memory timeline MVP",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
