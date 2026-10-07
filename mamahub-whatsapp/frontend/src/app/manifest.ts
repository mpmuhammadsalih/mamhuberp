import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "MamaHub WhatsApp CRM",
    short_name: "MamaHub WA",
    description: "WhatsApp sales inbox for MamaHub Trading",
    start_url: "/inbox",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#0b4d3a",
    theme_color: "#0b4d3a",
    lang: "en",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-192-maskable.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
