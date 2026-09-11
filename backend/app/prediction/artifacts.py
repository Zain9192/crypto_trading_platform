from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import UUID

from app.prediction.models import ModelBundle

FILES = ("forest.joblib", "xgboost.json", "sequence.keras")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def directory(self, version: str) -> Path:
        # Never accept registry paths or user filenames as executable artifact locations.
        normalized = str(UUID(version))
        directory = (self.root / normalized).resolve()
        if directory.parent != self.root:
            raise ValueError("Invalid model artifact path")
        return directory

    def save(self, version: str, bundle: ModelBundle, metadata: dict) -> str:
        directory = self.directory(version)
        directory.mkdir(parents=True, exist_ok=False)
        bundle.save(directory)
        manifest = {"version": version, "metadata": metadata,
                    "packages": {name: package_version(name) for name in
                                 ("scikit-learn", "xgboost", "tensorflow-cpu")},
                    "files": {name: digest(directory / name) for name in FILES}}
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, allow_nan=False))
        # The PostgreSQL registration occurs only after every immutable artifact is written.
        return digest(path)

    def load(self, version: str, checksum: str) -> tuple[ModelBundle, dict]:
        directory = self.directory(version)
        manifest_path = directory / "manifest.json"
        if digest(manifest_path) != checksum:
            raise ValueError("Model manifest checksum mismatch")
        manifest = json.loads(manifest_path.read_text())
        if manifest["version"] != version or set(manifest["files"]) != set(FILES):
            raise ValueError("Model manifest is inconsistent")
        for name in FILES:
            path = directory / name
            if path.is_symlink() or digest(path) != manifest["files"][name]:
                raise ValueError("Model artifact checksum mismatch")
        for name, expected in manifest["packages"].items():
            if package_version(name) != expected:
                raise ValueError(f"Model package version mismatch for {name}; use matching runtime or retrain")
        return cached_bundle(str(directory), checksum), manifest["metadata"]


@lru_cache(maxsize=4)
def cached_bundle(directory: str, checksum: str) -> ModelBundle:
    """Cache immutable versions; callers verify hashes before every use."""
    return ModelBundle.load(Path(directory))
