import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "МОСТ — задачи бизнеса и студенческие команды", description: "Опишите задачу, получите предложения студенческих команд и выберите партнёров.", icons: { icon: "/favicon.svg" } };
export default function RootLayout({ children }: {
    children: React.ReactNode;
}) { return <html lang="ru"><body>{children}</body></html>; }
