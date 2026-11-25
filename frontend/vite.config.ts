import { defineConfig, loadEnv, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

function patchDemodernizeSource(code: string): string | null {
  if (!code.includes("version 300 es") || !code.includes("demodernizeShader")) {
    return null;
  }
  const patched = code.replace(
    /output\s*=\s*output\.replaceAll\(`version 300 es`,\s*``\);/,
    "output = output.replaceAll(`version 300 es`, ``);\n  output = output.replaceAll(/\\b(?:flat|smooth|noperspective)\\s+(in|out|varying)\\b/g, `$1`);"
  );
  return patched !== code ? patched : null;
}

function cesiumWebgl1ShaderFixPlugin(): Plugin {
  return {
    name: "cesium-webgl1-shader-fix",
    transform(code, id) {
      if (id.includes("demodernizeShader")) {
        const patched = patchDemodernizeSource(code);
        if (patched) {
          return { code: patched, map: null };
        }
      }
      return null;
    },
  };
}

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, path.resolve(__dirname, ".."), "VITE_");
  const localEnv = loadEnv(mode, path.resolve(__dirname), "VITE_");

  const fallbackDefine: Record<string, string> = {};
  for (const key of [
    "VITE_CESIUM_ION_TOKEN",
    "VITE_GOOGLE_MAPS_API_KEY",
    "VITE_YOUTUBE_API_KEY",
    "VITE_WORLDOS_API",
  ]) {
    if (!rootEnv[key] && localEnv[key]) {
      fallbackDefine[`import.meta.env.${key}`] = JSON.stringify(localEnv[key]);
    }
  }

  return {
    plugins: [react(), cesiumWebgl1ShaderFixPlugin()],
    envDir: path.resolve(__dirname, ".."),
    define: fallbackDefine,
    optimizeDeps: {
      esbuildOptions: {
        plugins: [
          {
            name: "esbuild-cesium-webgl1-shader-fix",
            setup(build) {
              const fs = require("node:fs");
              build.onLoad({ filter: /demodernizeShader\.js$/ }, async (args) => {
                const contents = await fs.promises.readFile(args.path, "utf8");
                const patched = patchDemodernizeSource(contents);
                return { contents: patched ?? contents, loader: "js" };
              });
            },
          },
        ],
      },
    },
  };
});
