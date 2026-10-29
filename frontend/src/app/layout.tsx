import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/components/auth-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "機械租賃 ERP",
  description: "機械租賃營運管理平台",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "MR Field",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-HK">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
