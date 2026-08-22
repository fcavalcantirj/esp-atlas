"use client";

import { ThemeProvider } from "next-themes";
import { HelpTipProvider } from "@/components/HelpTipProvider";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem disableTransitionOnChange>
      <HelpTipProvider>{children}</HelpTipProvider>
    </ThemeProvider>
  );
}
