import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEV_MARKER_SCHEMA = "kbprep.dev_venv.v1";
const DEV_DEPENDENCY_SPEC = "editable-no-deps;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2;coverage[toml]>=7.6,<8;mypy>=1.17,<2;ruff>=0.8,<1";

export function kbprepVenvPythonPathForTest(rootDir) {
  return kbprepVenvPythonPath(rootDir);
}

function repoRootDir() {
  return resolve(dirname(fileURLToPath(import.meta.url)), "..");
}

function kbprepVenvDir(rootDir) {
  return join(rootDir, ".kbprep", "venv");
}

function kbprepVenvPythonPath(rootDir) {
  const venvDir = kbprepVenvDir(rootDir);
  return process.platform === "win32"
    ? join(venvDir, "Scripts", "python.exe")
    : join(venvDir, "bin", "python");
}

function devMarkerPath(rootDir) {
  return join(rootDir, ".kbprep", "dev-runtime-ready.json");
}

function packageVersion(rootDir) {
  const pkg = JSON.parse(readFileSync(join(rootDir, "package.json"), "utf8"));
  return String(pkg.version || "unknown");
}

function isDevRuntimeReady(rootDir) {
  if (!existsSync(kbprepVenvPythonPath(rootDir)) || !existsSync(devMarkerPath(rootDir))) {
    return false;
  }
  try {
    const marker = JSON.parse(readFileSync(devMarkerPath(rootDir), "utf8"));
    return marker.schema === DEV_MARKER_SCHEMA
      && marker.kbprep_version === packageVersion(rootDir)
      && marker.python_executable === kbprepVenvPythonPath(rootDir)
      && marker.dependency_spec === DEV_DEPENDENCY_SPEC;
  } catch {
    return false;
  }
}

function bootstrapCommand() {
  const override = process.env.KBPREP_BOOTSTRAP_PYTHON?.trim();
  if (override) return { command: override, args: [] };
  if (process.platform === "win32") return { command: "py", args: ["-3"] };
  return { command: "python3", args: [] };
}

function runRequired(command, args, rootDir, label) {
  const result = spawnSync(command, args, {
    cwd: rootDir,
    encoding: "utf8",
    stdio: "pipe",
    shell: false,
    env: {
      ...process.env,
      PIP_DISABLE_PIP_VERSION_CHECK: "1",
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    },
  });
  writeBootstrapOutput(result.stdout);
  writeBootstrapOutput(result.stderr);
  if (result.status === 0) return;
  throw new Error(`${label} failed with exit ${result.status ?? 1}`);
}

function writeBootstrapOutput(output) {
  if (!output) return;
  process.stderr.write(output);
}

function ensureDevRuntime(rootDir) {
  const pythonPath = kbprepVenvPythonPath(rootDir);
  mkdirSync(join(rootDir, ".kbprep"), { recursive: true });
  if (!existsSync(pythonPath)) {
    const bootstrap = bootstrapCommand();
    runRequired(bootstrap.command, [...bootstrap.args, "-m", "venv", kbprepVenvDir(rootDir)], rootDir, "create KBPrep venv");
  }
  if (isDevRuntimeReady(rootDir)) return pythonPath;

  runRequired(pythonPath, ["-m", "pip", "install", "--upgrade", "pip", "setuptools<82", "wheel"], rootDir, "upgrade KBPrep venv packaging");
  runRequired(pythonPath, ["-m", "pip", "install", "--no-deps", "-e", join(rootDir, "python")], rootDir, "install KBPrep worker editable");
  runRequired(
    pythonPath,
    [
      "-m",
      "pip",
      "install",
      "PyMuPDF>=1.27,<2",
      "pymupdf4llm>=0.0.27,<1",
      "beautifulsoup4==4.14.3",
      "lxml==6.0.2",
      "coverage[toml]>=7.6,<8",
      "mypy>=1.17,<2",
      "ruff>=0.8,<1",
    ],
    rootDir,
    "install KBPrep dev tools",
  );
  writeFileSync(devMarkerPath(rootDir), JSON.stringify({
    schema: DEV_MARKER_SCHEMA,
    kbprep_version: packageVersion(rootDir),
    python_executable: pythonPath,
    dependency_spec: DEV_DEPENDENCY_SPEC,
    created_at: new Date().toISOString(),
  }, null, 2), "utf8");
  return pythonPath;
}

function envForVenv(rootDir) {
  const venvBin = process.platform === "win32"
    ? join(kbprepVenvDir(rootDir), "Scripts")
    : join(kbprepVenvDir(rootDir), "bin");
  const pythonPath = join(rootDir, "python");
  return {
    ...process.env,
    PATH: `${venvBin}${process.platform === "win32" ? ";" : ":"}${process.env.PATH || ""}`,
    PYTHONPATH: process.env.PYTHONPATH ? `${pythonPath}${process.platform === "win32" ? ";" : ":"}${process.env.PYTHONPATH}` : pythonPath,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  };
}

function main() {
  const rootDir = repoRootDir();
  const args = process.argv.slice(2);
  if (args[0] === "--print-python") {
    process.stdout.write(`${kbprepVenvPythonPath(rootDir)}\n`);
    return;
  }
  if (args.length === 0) {
    process.stderr.write("Usage: node scripts/python-venv.mjs <python args...>\n");
    process.exit(2);
  }

  const pythonPath = ensureDevRuntime(rootDir);
  const result = spawnSync(pythonPath, args, {
    cwd: rootDir,
    stdio: "inherit",
    shell: false,
    env: envForVenv(rootDir),
  });
  process.exit(result.status ?? 1);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
