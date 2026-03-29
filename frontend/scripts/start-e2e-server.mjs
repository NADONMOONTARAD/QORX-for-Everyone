import { spawn } from "child_process";

const env = {
  ...process.env,
  NEXT_TELEMETRY_DISABLED: "1",
};

const npxCommand = process.platform === "win32" ? "npx.cmd" : "npx";
const useShell = process.platform === "win32";

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env,
      stdio: "inherit",
      shell: useShell,
    });

    child.on("exit", (code, signal) => {
      if (signal) {
        reject(new Error(`Command terminated with signal ${signal}`));
        return;
      }
      if (code !== 0) {
        reject(new Error(`Command failed with exit code ${code}`));
        return;
      }
      resolve();
    });
  });
}

await run(npxCommand, ["next", "build"]);

const server = spawn(
  npxCommand,
  ["next", "start", "--hostname", "127.0.0.1", "--port", "3100"],
  {
    cwd: process.cwd(),
    env,
    stdio: "inherit",
    shell: useShell,
  },
);

server.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
