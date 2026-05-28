import subprocess
import sys
from pathlib import Path

def main() -> None:
    if len(sys.argv) < 3:
        print("usage: clone.py <dest_dir> <repo_url>", file=sys.stderr)
        sys.exit(2)
    dest, url = Path(sys.argv[1]), sys.argv[2]
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    sys.exit(proc.returncode)

if __name__ == "__main__":
    main()
