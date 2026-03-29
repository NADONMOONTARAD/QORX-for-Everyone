const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const candidates = [
  path.join(repoRoot, ".venv", "Scripts", "python.exe"),
  path.join(repoRoot, ".venv", "bin", "python"),
];

const python = candidates.find((candidate) => fs.existsSync(candidate));

if (!python) {
  console.error(
    "Local virtualenv not found. Create .venv first with `python -m venv .venv`.",
  );
  process.exit(1);
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("No Python arguments provided.");
  process.exit(1);
}

const child = spawn(python, args, {
  cwd: repoRoot,
  env: process.env,
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(error.message);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 1);
});
