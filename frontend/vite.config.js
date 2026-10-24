import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server proxies /api to FastAPI so the frontend never needs an API key
// or absolute URL (keys live only on the server — see backend/.env).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Backend down -> Vite's default is a bare 500 (opaque to the UI).
        // Answer with a readable JSON error instead, shaped like FastAPI's
        // {detail, error_type} so client.js surfaces a real message.
        configure(proxy) {
          proxy.on("error", (err, req, res) => {
            if (!res || res.headersSent || typeof res.writeHead !== "function") return;
            try {
              res.writeHead(502, { "Content-Type": "application/json" });
              res.end(
                JSON.stringify({
                  detail:
                    "Backend unreachable — FastAPI is not running on port 8000. " +
                    "Start it in backend/: uvicorn app.main:app --port 8000",
                  error_type: "backend_unreachable",
                })
              );
            } catch {
              /* client already disconnected */
            }
          });
        },
      },
    },
  },
});
