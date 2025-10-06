import subprocess
import sys
import os

SOURCE_FILES = [
    "PaymentProcessor.py",
    "KeyManager.py",
    "CryptoLedger.py",
    "JSONFactory.py",
    "MandateFactory.py",
    "MandateSigner.py",
]

ENTRY_FILE = "Main.py"

def compile_with_nuitka(entry_file: str, extra_modules: list, output_dir: str = "dist"):
    if not os.path.isfile(entry_file):
        print(f"[Error] Entry file '{entry_file}' not found.")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "nuitka",
        entry_file,
        "--output-dir=" + output_dir,
        "--remove-output",
        "--follow-imports",
        "--standalone",
        "--onefile",
        "--enable-plugin=pylint-warnings",
        "--show-modules",
    ]

    for module in extra_modules:
        mod_name = os.path.splitext(os.path.basename(module))[0]
        cmd.append(f"--include-module={mod_name}")

    print("[Build] Compiling with Nuitka...")
    subprocess.run(cmd, check=True)
    print("[Build] Compilation finished.")

if __name__ == "__main__":
    compile_with_nuitka(ENTRY_FILE, SOURCE_FILES)
