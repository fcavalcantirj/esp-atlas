import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { contributingUrl, dataFolderUrl, repoUrl } from "@/lib/github";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "esp-atlas",
  description: "Which ESP32 for what you're building?",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="site-logo">
              esp-atlas
            </Link>
            <nav className="site-nav">
              <Link href="/compare">compare</Link>
              <a href={contributingUrl()} target="_blank" rel="noreferrer">
                Add a part
              </a>
              <a href={repoUrl()} target="_blank" rel="noreferrer" className="contribute-link">
                Contribute on GitHub
              </a>
            </nav>
          </div>
        </header>
        {children}
        <footer className="site-footer">
          <div className="site-footer-inner">
            <a href={dataFolderUrl()} target="_blank" rel="noreferrer">
              Browse data on GitHub
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
