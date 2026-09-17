import boto3
import pytest
from moto import mock_aws

from aws_deployment_toolkit.s3_sync import S3Syncer

REGION = "us-east-1"


def _write(path, name, content):
    p = path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@mock_aws
def test_sync_creates_missing_bucket(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    syncer = S3Syncer(region_name=REGION)
    bucket = "brand-new-bucket"

    assert not syncer.bucket_exists(bucket)
    plan = syncer.sync(str(tmp_path), bucket)

    assert plan.bucket_created is True
    assert syncer.bucket_exists(bucket)


@mock_aws
def test_sync_uploads_new_files(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    _write(tmp_path, "sub/b.txt", "world")
    syncer = S3Syncer(region_name=REGION)
    bucket = "my-upload-bucket"

    plan = syncer.sync(str(tmp_path), bucket)

    assert sorted(plan.to_upload_new) == ["a.txt", "sub/b.txt"]
    assert plan.to_upload_changed == []
    keys = {o["Key"] for o in syncer.s3.list_objects_v2(Bucket=bucket)["Contents"]}
    assert keys == {"a.txt", "sub/b.txt"}


@mock_aws
def test_sync_skips_unchanged_files(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    syncer = S3Syncer(region_name=REGION)
    bucket = "unchanged-bucket"

    syncer.sync(str(tmp_path), bucket)  # first sync uploads it
    plan2 = syncer.sync(str(tmp_path), bucket)  # nothing changed

    assert plan2.to_upload_new == []
    assert plan2.to_upload_changed == []
    assert plan2.unchanged == ["a.txt"]


@mock_aws
def test_sync_uploads_changed_files(tmp_path):
    path = _write(tmp_path, "a.txt", "hello")
    syncer = S3Syncer(region_name=REGION)
    bucket = "changed-bucket"

    syncer.sync(str(tmp_path), bucket)
    path.write_text("hello, world -- this content changed!")
    plan2 = syncer.sync(str(tmp_path), bucket)

    assert plan2.to_upload_changed == ["a.txt"]
    assert plan2.to_upload_new == []

    body = syncer.s3.get_object(Bucket=bucket, Key="a.txt")["Body"].read()
    assert body == b"hello, world -- this content changed!"


@mock_aws
def test_dry_run_makes_no_changes(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    syncer = S3Syncer(region_name=REGION)
    bucket = "dry-run-bucket"

    plan = syncer.sync(str(tmp_path), bucket, dry_run=True)

    assert plan.to_upload_new == ["a.txt"]
    # Bucket must NOT have been created, since dry-run must not touch AWS.
    assert not syncer.bucket_exists(bucket)


@mock_aws
def test_dry_run_reports_changed_file_without_uploading(tmp_path):
    path = _write(tmp_path, "a.txt", "hello")
    syncer = S3Syncer(region_name=REGION)
    bucket = "dry-run-bucket-2"

    syncer.sync(str(tmp_path), bucket)  # real upload
    path.write_text("changed content")
    plan = syncer.sync(str(tmp_path), bucket, dry_run=True)

    assert plan.to_upload_changed == ["a.txt"]
    # Object in S3 must still have the OLD content since this was dry-run.
    body = syncer.s3.get_object(Bucket=bucket, Key="a.txt")["Body"].read()
    assert body == b"hello"


@mock_aws
def test_sync_raises_clean_error_for_missing_local_dir():
    syncer = S3Syncer(region_name=REGION)
    with pytest.raises(FileNotFoundError):
        syncer.sync("/path/does/not/exist/at/all", "some-bucket")
