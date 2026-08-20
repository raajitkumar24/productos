import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "ProductOS",
  description: "Evidence-first product intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
