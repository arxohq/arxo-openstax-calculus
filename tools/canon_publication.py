#!/usr/bin/env python3
"""Build and verify a deliberately small, public canon release.

The input is a private checkout and an exact allowlist in ``publication.toml``.
This program does not infer package contents, contact a forge, or copy Git
history.  Its output can therefore be handed to a separately authorised
publication job without granting that job access to the private checkout.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import tomllib
from typing import Any
import re


CONFIG_FORMAT = "law.canon-publication/1"
MANIFEST_FORMAT = "law.canon-manifest/1"
MANIFEST_NAME = "CANON-MANIFEST.json"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
                    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
GITHUB_REPOSITORY = re.compile(
    r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9._-]{0,38}[A-Za-z0-9])?)/"
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?)$")


class PublicationError(ValueError):
    """The requested public artifact is invalid or unsafe to produce."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicationError(f"{field}: expected a non-empty path")
    if "\\" in value:
        raise PublicationError(f"{field}: paths must use POSIX separators: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
        raise PublicationError(f"{field}: unsafe path {value!r}")
    if value == MANIFEST_NAME:
        raise PublicationError(f"{field}: {MANIFEST_NAME} is generated")
    return path.as_posix()


def _strings(config: dict[str, Any], key: str, *, nonempty: bool = True) -> list[str]:
    value = config.get(key)
    if not isinstance(value, list) or (nonempty and not value):
        raise PublicationError(f"{key}: expected a non-empty array")
    if not all(isinstance(item, str) and item for item in value):
        raise PublicationError(f"{key}: expected non-empty strings")
    if len(set(value)) != len(value):
        raise PublicationError(f"{key}: duplicate values are not allowed")
    return value


def _released_at(value: str) -> str:
    """Accept an explicit, timezone-aware ISO-8601 release instant only."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PublicationError("releasedAt: expected an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise PublicationError("releasedAt: expected a timezone-aware timestamp")
    return value


def _version(value: str) -> str:
    if not SEMVER.fullmatch(value):
        raise PublicationError("version: expected a safe semantic version")
    return value


def _repository(value: str) -> str:
    if not GITHUB_REPOSITORY.fullmatch(value):
        raise PublicationError("repository: expected canonical HTTPS GitHub owner/repository URL")
    return value


def _no_symlink_ancestor(path: Path, label: str) -> None:
    """Do not silently escape a private checkout or destination through a link."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise PublicationError(f"{label} has a symlink ancestor: {current}")


def read_config(path: Path) -> dict[str, Any]:
    """Read and validate the public subset of a publication declaration."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PublicationError(f"cannot read publication config {path}: {error}") from error
    if raw.get("format") != CONFIG_FORMAT:
        raise PublicationError(f"format: expected {CONFIG_FORMAT!r}")
    allowed_keys = {"format", "version", "repository", "releasedAt", "packages", "files", "requiredFiles"}
    unexpected = sorted(set(raw) - allowed_keys)
    if unexpected:
        raise PublicationError(f"publication config has unknown fields: {', '.join(unexpected)}")
    result: dict[str, Any] = {"format": raw["format"]}
    for key in ("version", "repository", "releasedAt"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PublicationError(f"{key}: expected a non-empty string")
        result[key] = value
    result["version"] = _version(result["version"])
    result["repository"] = _repository(result["repository"])
    result["releasedAt"] = _released_at(result["releasedAt"])
    result["packages"] = _strings(raw, "packages")
    result["files"] = [_relative_path(item, "files") for item in _strings(raw, "files")]
    if len(set(result["files"])) != len(result["files"]):
        raise PublicationError("files: duplicate normalized paths are not allowed")
    result["requiredFiles"] = [_relative_path(item, "requiredFiles")
                               for item in _strings(raw, "requiredFiles")]
    if not set(result["requiredFiles"]).issubset(result["files"]):
        raise PublicationError("requiredFiles: every required path must be allowlisted in files")
    return result


def _source_file(source: Path, rel: str) -> Path:
    """Return a regular file below source, refusing any symlink on its path."""
    current = source
    try:
        if current.is_symlink() or not current.is_dir():
            raise PublicationError(f"source is not a real directory: {source}")
        for part in PurePosixPath(rel).parts:
            current = current / part
            if current.is_symlink():
                raise PublicationError(f"symlink is not publishable: {rel}")
        file_stat = current.stat()
    except OSError as error:
        raise PublicationError(f"allowlisted file is missing: {rel}") from error
    if not current.is_file() or not stat.S_ISREG(file_stat.st_mode):
        raise PublicationError(f"allowlisted path is not a regular file: {rel}")
    return current


def _manifest(config: dict[str, Any], source: Path) -> dict[str, Any]:
    files = []
    for rel in sorted(config["files"]):
        data = _source_file(source, rel).read_bytes()
        files.append({"path": rel, "sha256": _sha256(data), "size": len(data)})
    return {
        "files": files,
        "format": MANIFEST_FORMAT,
        "packages": sorted(config["packages"]),
        "releasedAt": config["releasedAt"],
        "repository": config["repository"],
        "requiredFiles": sorted(config["requiredFiles"]),
        "version": config["version"],
    }


def _check_lock_resources(root: Path, paths: list[str]) -> None:
    """Every resource pinned by a published ``law.lock`` ships in the release.

    A row that leaves its package (``../`` into the development monorepo) or
    names a file outside the allowlist resolves in the private checkout and is
    dead in the public one. A calendar dataset is pinned by its raw bytes, so a
    stale ``contentHash`` is refused here too; decision tables are hashed in
    canonical form and are checked by the toolchain, not by this program.
    """
    listed = set(paths)
    for rel in sorted(listed):
        if PurePosixPath(rel).name != "law.lock":
            continue
        try:
            lock = json.loads(_source_file(root, rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PublicationError(f"{rel}: unreadable lock: {error}") from error
        rows = lock.get("resources", []) if isinstance(lock, dict) else None
        if not isinstance(rows, list):
            raise PublicationError(f"{rel}: resources must be an array")
        for row in rows:
            value = row.get("path") if isinstance(row, dict) else None
            path = PurePosixPath(value) if isinstance(value, str) and value and "\\" not in value else None
            if path is None or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise PublicationError(f"{rel}: resource path leaves the package: {value!r}")
            target = (PurePosixPath(rel).parent / path).as_posix()
            if target not in listed:
                raise PublicationError(f"{rel}: resource {value} is not allowlisted")
            if (row.get("kind") == "calendar-dataset"
                    and _sha256(_source_file(root, target).read_bytes()) != row.get("contentHash")):
                raise PublicationError(f"{rel}: resource {value} differs from its contentHash")


def validate(source: Path, config_path: Path) -> dict[str, Any]:
    """Validate a private checkout's declaration without creating an artifact."""
    source = source.resolve()
    _no_symlink_ancestor(source, "source")
    config = read_config(config_path)
    manifest = _manifest(config, source)
    _check_lock_resources(source, config["files"])
    return manifest


def export(source: Path, config_path: Path, out: Path) -> dict[str, Any]:
    """Create a new release directory. Existing destinations are never merged."""
    # Canonicalize OS-level aliases (for example macOS /var -> /private/var)
    # before containment checks. Explicit publication paths are still rejected
    # if a symlink occurs below this canonical root.
    source = source.resolve()
    out = out.resolve()
    _no_symlink_ancestor(out, "output")
    if out.is_relative_to(source):
        raise PublicationError("output must be outside the private source directory")
    if out.exists() or out.is_symlink():
        raise PublicationError(f"output must be a new directory: {out}")
    manifest = validate(source, config_path)  # validate everything before writing
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".canon-publication-", dir=out.parent))
    try:
        for entry in manifest["files"]:
            target = staging / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_source_file(source, entry["path"]), target)
        (staging / MANIFEST_NAME).write_bytes(_json_bytes(manifest))
        # A final verification also protects against a concurrently modified source.
        verify(staging)
        staging.rename(out)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def verify(artifact: Path) -> dict[str, Any]:
    """Verify exact inventory and hashes without any private source checkout."""
    artifact = artifact.resolve()
    _no_symlink_ancestor(artifact, "artifact")
    try:
        manifest = json.loads(_source_file(artifact, MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot read {MANIFEST_NAME}: {error}") from error
    expected_keys = {"files", "format", "packages", "releasedAt", "repository", "requiredFiles", "version"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys or manifest.get("format") != MANIFEST_FORMAT:
        raise PublicationError(f"{MANIFEST_NAME}: unsupported format")
    for key in ("version", "repository", "releasedAt"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise PublicationError(f"{MANIFEST_NAME}: invalid {key}")
    _version(manifest["version"])
    _repository(manifest["repository"])
    _released_at(manifest["releasedAt"])
    for key in ("packages", "requiredFiles", "files"):
        if not isinstance(manifest.get(key), list) or not manifest[key]:
            raise PublicationError(f"{MANIFEST_NAME}: invalid {key}")
    if (not all(isinstance(item, str) and item for item in manifest["packages"])
            or len(set(manifest["packages"])) != len(manifest["packages"])):
        raise PublicationError(f"{MANIFEST_NAME}: invalid packages")
    if manifest["packages"] != sorted(manifest["packages"]):
        raise PublicationError(f"{MANIFEST_NAME}: packages must be sorted")
    allowed = {MANIFEST_NAME}
    listed: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise PublicationError(f"{MANIFEST_NAME}: invalid file entry")
        rel = _relative_path(entry.get("path"), "manifest files")
        if rel in listed or set(entry) != {"path", "sha256", "size"}:
            raise PublicationError(f"{MANIFEST_NAME}: duplicate or malformed entry {rel!r}")
        if (not isinstance(entry["sha256"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", entry["sha256"])
                or isinstance(entry["size"], bool) or not isinstance(entry["size"], int)
                or entry["size"] < 0):
            raise PublicationError(f"{MANIFEST_NAME}: invalid digest for {rel}")
        path = _source_file(artifact, rel)
        data = path.read_bytes()
        if len(data) != entry["size"] or _sha256(data) != entry["sha256"]:
            raise PublicationError(f"artifact bytes differ: {rel}")
        listed.add(rel)
        allowed.add(rel)
    required = [_relative_path(item, "manifest requiredFiles") for item in manifest["requiredFiles"]]
    if len(set(required)) != len(required) or not set(required).issubset(listed):
        raise PublicationError(f"{MANIFEST_NAME}: requiredFiles do not match files")
    if required != sorted(required) or [entry["path"] for entry in manifest["files"]] != sorted(listed):
        raise PublicationError(f"{MANIFEST_NAME}: file lists must be sorted")
    inventory: set[str] = set()
    for path in artifact.rglob("*"):
        rel = path.relative_to(artifact).as_posix()
        if ".git" in path.relative_to(artifact).parts:
            raise PublicationError(f"artifact contains forbidden .git path: {rel}")
        if path.is_symlink():
            raise PublicationError(f"artifact contains symlink: {rel}")
        if not path.is_file() and not path.is_dir():
            raise PublicationError(f"artifact contains unsupported filesystem object: {rel}")
        if path.is_file():
            inventory.add(rel)
    if inventory != allowed:
        raise PublicationError("artifact inventory differs from manifest")
    _check_lock_resources(artifact, sorted(listed))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    export_parser = actions.add_parser("export")
    export_parser.add_argument("--source", required=True, type=Path)
    export_parser.add_argument("--config", required=True, type=Path)
    export_parser.add_argument("--out", required=True, type=Path)
    verify_parser = actions.add_parser("verify")
    verify_parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = (export(args.source, args.config, args.out) if args.action == "export"
                  else verify(args.artifact))
    except PublicationError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
