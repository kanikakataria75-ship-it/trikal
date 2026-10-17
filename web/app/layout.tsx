import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono, Instrument_Serif, Tiro_Devanagari_Hindi } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";

const inter = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-instrument", display: "swap" });
const deva = Tiro_Devanagari_Hindi({ subsets: ["devanagari", "latin"], weight: "400", variable: "--font-tiro", display: "swap" });

export const metadata: Metadata = {
  title: "TRIKAL — Indian equity research, as it was known",
  description: "Point-in-time Indian equity research terminal. Survivorship-free, sector-correct, honest about time.",
};

export const viewport: Viewport = { themeColor: "#07080A" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${serif.variable} ${deva.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
