import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const candidates = process.platform === "win32"
  ? [".venv/Scripts/python.exe", "python"]
  : [".venv/bin/python", "python"];
const python = candidates.find((candidate) => candidate === "python" || existsSync(candidate));
const result = spawnSync(python, process.argv.slice(2), { stdio: "inherit" });

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
