"""S3 directory sync with real incremental-upload logic.

The sync compares the MD5 hash of each local file against the ETag of the
corresponding S3 object. For objects uploaded with a simple (non-multipart)
PutObject call -- which is what this toolkit always uses -- S3's ETag is
exactly the hex-encoded MD5 digest of the object body, wrapped in quotes.
That means we can detect "unchanged" files without downloading them: hash
the local file, strip the quotes off the remote ETag, and compare strings.

Only new or changed files are uploaded. Unchanged files are skipped. A
dry-run mode computes the same plan without touching S3 at all.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def _md5_hex(path: Path, chunk_size: int = 8192) -> str:
    """Return the hex MD5 digest of a local file's contents."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_local_files(local_dir: Path):
    for root, _dirs, files in os.walk(local_dir):
        for name in files:
            full = Path(root) / name
            rel = full.relative_to(local_dir).as_posix()
            yield rel, full


@dataclass
class SyncPlan:
    """The set of actions a sync would take (or took)."""

    to_upload_new: list = field(default_factory=list)
    to_upload_changed: list = field(default_factory=list)
    unchanged: list = field(default_factory=list)
    bucket_created: bool = False

    @property
    def total_changes(self) -> int:
        return len(self.to_upload_new) + len(self.to_upload_changed)

    def summary(self) -> str:
        lines = []
        if self.bucket_created:
            lines.append("Bucket did not exist and would be/was created.")
        lines.append(f"New files to upload:      {len(self.to_upload_new)}")
        lines.append(f"Changed files to upload:  {len(self.to_upload_changed)}")
        lines.append(f"Unchanged files (skipped): {len(self.unchanged)}")
        for key in self.to_upload_new:
            lines.append(f"  [NEW]     {key}")
        for key in self.to_upload_changed:
            lines.append(f"  [CHANGED] {key}")
        return "\n".join(lines)


class S3Syncer:
    """Syncs a local directory to an S3 bucket, uploading only diffs."""

    def __init__(self, s3_client=None, region_name: str | None = None):
        self.s3 = s3_client or boto3.client("s3", region_name=region_name)
        self._region = region_name

    def bucket_exists(self, bucket: str) -> bool:
        try:
            self.s3.head_bucket(Bucket=bucket)
            return True
        except ClientError:
            return False

    def ensure_bucket(self, bucket: str) -> bool:
        """Create the bucket if it doesn't exist. Returns True if created."""
        if self.bucket_exists(bucket):
            return False
        region = self._region or self.s3.meta.region_name
        if region and region != "us-east-1":
            self.s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        else:
            self.s3.create_bucket(Bucket=bucket)
        return True

    def _remote_etags(self, bucket: str, prefix: str = "") -> dict:
        etags = {}
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                etags[obj["Key"]] = obj["ETag"].strip('"')
        return etags

    def build_plan(self, local_dir: str, bucket: str, prefix: str = "") -> SyncPlan:
        """Compute what would change, without uploading anything."""
        local_path = Path(local_dir)
        if not local_path.is_dir():
            if local_path.exists():
                raise FileNotFoundError(
                    f"Expected a directory but found a file: {local_dir}"
                )
            raise FileNotFoundError(f"Local directory does not exist: {local_dir}")

        plan = SyncPlan()
        bucket_exists = self.bucket_exists(bucket)
        plan.bucket_created = not bucket_exists

        remote_etags = self._remote_etags(bucket, prefix) if bucket_exists else {}

        for rel_path, full_path in _iter_local_files(local_path):
            key = f"{prefix.rstrip('/')}/{rel_path}" if prefix else rel_path
            local_hash = _md5_hex(full_path)
            remote_etag = remote_etags.get(key)
            if remote_etag is None:
                plan.to_upload_new.append(key)
            elif remote_etag != local_hash:
                plan.to_upload_changed.append(key)
            else:
                plan.unchanged.append(key)
        return plan

    def sync(self, local_dir: str, bucket: str, prefix: str = "", dry_run: bool = False) -> SyncPlan:
        """Sync local_dir to bucket/prefix. Uploads only new/changed files.

        When dry_run is True, no bucket is created and no objects are
        uploaded -- the returned plan describes what WOULD happen.
        """
        plan = self.build_plan(local_dir, bucket, prefix)

        if dry_run:
            return plan

        if plan.bucket_created:
            self.ensure_bucket(bucket)

        local_path = Path(local_dir)
        changed_keys = set(plan.to_upload_new) | set(plan.to_upload_changed)
        for rel_path, full_path in _iter_local_files(local_path):
            key = f"{prefix.rstrip('/')}/{rel_path}" if prefix else rel_path
            if key in changed_keys:
                self.s3.upload_file(str(full_path), bucket, key)
        return plan


def sync_directory(local_dir: str, bucket: str, prefix: str = "", dry_run: bool = False,
                    s3_client=None, region_name: str | None = None) -> SyncPlan:
    """Convenience function wrapping S3Syncer for CLI use."""
    syncer = S3Syncer(s3_client=s3_client, region_name=region_name)
    return syncer.sync(local_dir, bucket, prefix=prefix, dry_run=dry_run)
