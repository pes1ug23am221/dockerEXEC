import os
import shutil
import zipfile
from pathlib import Path
from typing import List

MAX_TOTAL_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_FILES_COUNT = 10_000


class ExtractionSecurityError(Exception):
    """Raised when an archive violates security constraints."""
    pass


def extract_job(zip_path: Path, destination: Path) -> List[Path]:
    """
    Safely extract a ZIP archive into the destination directory.
    Protects against Zip Slip (traversal), decompression bombs, and dangerous symlinks.
    If archive contains a single top-level directory, its contents are flattened to the destination root.
    """
    zip_path = Path(zip_path).resolve()
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    if not zip_path.is_file():
        raise FileNotFoundError(f"Source archive not found: {zip_path}")

    total_uncompressed_size = 0
    extracted_paths: List[Path] = []

    with zipfile.ZipFile(zip_path, "r") as archive:
        infolist = archive.infolist()

        if len(infolist) > MAX_FILES_COUNT:
            raise ExtractionSecurityError(
                f"Archive contains too many files ({len(infolist)} > {MAX_FILES_COUNT})"
            )

        # First pass: validate all archive members before extracting
        for member in infolist:
            total_uncompressed_size += member.file_size
            if total_uncompressed_size > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise ExtractionSecurityError(
                    f"Archive exceeds maximum allowed uncompressed size ({MAX_TOTAL_UNCOMPRESSED_SIZE} bytes)"
                )

            # Prevent Zip Slip / directory traversal
            target_path = (destination / member.filename).resolve()
            try:
                # Must be relative to destination
                target_path.relative_to(destination)
            except ValueError:
                raise ExtractionSecurityError(
                    f"Malicious member path detected (Zip Slip): {member.filename}"
                )

        # Second pass: safe extraction
        for member in infolist:
            target_path = (destination / member.filename).resolve()

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_paths.append(target_path)

    # Flatten if zip was wrapped in a single root folder
    entries = [p for p in destination.iterdir() if p.name != "metadata.json"]
    if len(entries) == 1 and entries[0].is_dir():
        wrapper_dir = entries[0]
        temp_dir = destination.parent / f"_tmp_{destination.name}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        for item in wrapper_dir.iterdir():
            shutil.move(str(item), str(temp_dir))

        shutil.rmtree(destination)
        temp_dir.rename(destination)

    return extracted_paths
