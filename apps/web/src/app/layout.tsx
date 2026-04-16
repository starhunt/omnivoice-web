import type { Metadata } from "next";
import "@/styles/globals.css";
import { Sidebar } from "@/components/sidebar";

export const metadata: Metadata = {
  title: "OmniVoice Web",
  description: "자체 호스팅 음성 합성 플랫폼",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body className="min-h-screen bg-background">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 overflow-x-hidden">{children}</main>
        </div>
      </body>
    </html>
  );
}
