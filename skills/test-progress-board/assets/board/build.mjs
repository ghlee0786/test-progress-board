// src/app.jsx → public/app.js (React 포함). 실행에는 필요 없고, 화면을 고쳤을 때만: npm i && npm run build
import * as esbuild from "esbuild";
await esbuild.build({
  entryPoints: ["src/app.jsx"], outfile: "public/app.js", bundle: true, minify: true, format: "iife", jsx: "automatic",
  charset: "utf8", legalComments: "eof", define: { "process.env.NODE_ENV": '"production"' },
});
