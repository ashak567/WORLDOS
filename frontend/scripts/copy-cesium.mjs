import { cpSync, mkdirSync } from "node:fs";

mkdirSync("public", { recursive: true });
cpSync("node_modules/cesium/Build/Cesium", "public/cesium", { recursive: true });

