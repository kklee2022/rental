import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "機械租賃倉務物流",
    short_name: "MR Field",
    description: "機械租賃倉務、運輸及現場交收",
    start_url: "/logistics/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f3f5f1",
    theme_color: "#17201d",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
