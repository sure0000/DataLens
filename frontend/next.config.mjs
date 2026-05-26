import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootEnv = resolve(__dirname, "..", ".env");

/** 将项目根目录 .env 中的 NEXT_PUBLIC_* 注入 Next（dev 时 frontend/ 下无 .env 也能读到） */
function loadRootPublicEnv() {
  if (!existsSync(rootEnv)) return {};
  const out = {};
  for (const line of readFileSync(rootEnv, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    if (!key.startsWith("NEXT_PUBLIC_")) continue;
    let val = trimmed.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: loadRootPublicEnv(),
};

export default nextConfig;
