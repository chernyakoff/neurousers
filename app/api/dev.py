import subprocess
import sys

from watchfiles import run_process

GRACEFUL_TIMEOUT = 3


def target():
    proc = subprocess.Popen([sys.executable, "-m", "api"])
    try:
        proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=GRACEFUL_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    run_process(".", target=target)
