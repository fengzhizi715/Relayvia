"""Worker boot regression: the standalone Worker process must be able to
configure every ORM mapper before its first queue query. Tests import all
models via conftest, so this runs in a fresh subprocess to catch missing
model registration in the real entry point."""

import subprocess
import sys
from pathlib import Path


def test_worker_import_registers_all_orm_mappers():
    backend_dir = Path(__file__).resolve().parents[1]
    code = (
        "import app.workers.workflow_worker; "
        "from sqlalchemy.orm import configure_mappers; "
        "configure_mappers()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
