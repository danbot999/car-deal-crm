import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auckland Car Deal CRM",
  description: "Local CRM dashboard for Marketplace car deal analysis"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-NZ">
      <body>{children}</body>
    </html>
  );
}
