import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SAP Knowledge AI Assistant",
  description: "Enterprise RAG-based AI assistant for SAP Functional and Technical consulting.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
        <style>{`
          body {
            font-family: 'Plus Jakarta Sans', 'Outfit', sans-serif;
          }
        `}</style>
      </head>
      <body className="h-full bg-[#05070e] text-[#f1f5f9] antialiased overflow-hidden selection:bg-purple-600/30 selection:text-purple-200" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
