import os
import subprocess
import sys
from pathlib import Path

import psutil

from nyx.single import take_over


def test_writes_own_pid_and_ignores_dead_or_foreign(tmp_path: Path) -> None:
    path = tmp_path / "core.pid"
    assert not take_over(path)
    assert path.read_text() == str(os.getpid())
    path.write_text("999999")  # ya no existe
    assert not take_over(path)
    # Un proceso vivo que no es un núcleo de Nyx no se toca.
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        path.write_text(str(other.pid))
        assert not take_over(path)
        assert psutil.pid_exists(other.pid) and other.poll() is None
    finally:
        other.kill()


def test_closes_a_previous_nyx_core(tmp_path: Path) -> None:
    path = tmp_path / "core.pid"
    # Simula un núcleo viejo lanzado por la app.
    old = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--parent-pipe"])
    try:
        path.write_text(str(old.pid))
        assert take_over(path)
        assert old.wait(timeout=5) is not None
        assert path.read_text() == str(os.getpid())
    finally:
        if old.poll() is None:
            old.kill()
