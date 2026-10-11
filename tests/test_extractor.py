import io
import zipfile
import pytest
from pathlib import Path
from executor.extractor import extract_job, ExtractionSecurityError


def test_safe_extraction_valid(tmp_path):
    zip_path = tmp_path / "valid.zip"
    dest_dir = tmp_path / "dest"

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("run.sh", "#!/bin/bash\necho test\n")
        z.writestr("subdir/script.py", "print('hello')\n")

    extracted = extract_job(zip_path, dest_dir)
    assert (dest_dir / "run.sh").is_file()
    assert (dest_dir / "subdir" / "script.py").is_file()


def test_zip_slip_prevention(tmp_path):
    zip_path = tmp_path / "malicious.zip"
    dest_dir = tmp_path / "dest"

    with zipfile.ZipFile(zip_path, "w") as z:
        # Create Zip Slip attempt
        z.writestr("../../evil.sh", "#!/bin/bash\necho evil\n")

    with pytest.raises(ExtractionSecurityError, match="Malicious member path detected"):
        extract_job(zip_path, dest_dir)


def test_flattening_single_root_folder(tmp_path):
    zip_path = tmp_path / "wrapped.zip"
    dest_dir = tmp_path / "dest"

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("project_folder/run.sh", "#!/bin/bash\n")
        z.writestr("project_folder/data.txt", "123\n")

    extract_job(zip_path, dest_dir)
    # Check that contents were flattened to destination root
    assert (dest_dir / "run.sh").is_file()
    assert (dest_dir / "data.txt").is_file()
