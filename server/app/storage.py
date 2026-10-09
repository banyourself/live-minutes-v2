import os
import re
import shutil
import tempfile

from .settings import settings


def _safe(key):
    if not re.fullmatch(r"[A-Za-z0-9_\-./ ]+", key) or ".." in key or key.startswith("/"):
        raise ValueError("bad storage key")
    return key


class LocalStorage:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, key):
        return os.path.join(self.root, *_safe(key).split("/"))

    def put(self, key, data):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return key

    def get(self, key):
        with open(self._path(key), "rb") as fh:
            return fh.read()

    def put_file(self, key, src):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(src, path)
        return key

    def size(self, key):
        return os.path.getsize(self._path(key))

    def read_range(self, key, start, end, chunk=1024 * 1024):
        with open(self._path(key), "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                data = fh.read(min(chunk, left))
                if not data:
                    break
                left -= len(data)
                yield data

    def delete_prefix(self, prefix):
        shutil.rmtree(self._path(prefix.rstrip("/")), ignore_errors=True)

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def local_copy(self, key, workdir):
        return self._path(key)


class S3Storage:
    def __init__(self, bucket):
        import boto3
        self.bucket = bucket
        self.s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None)

    def put(self, key, data):
        self.s3.put_object(Bucket=self.bucket, Key=_safe(key), Body=data, ServerSideEncryption="AES256")
        return key

    def get(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=_safe(key))["Body"].read()

    def put_file(self, key, src):
        self.s3.upload_file(src, self.bucket, _safe(key), ExtraArgs={"ServerSideEncryption": "AES256"})
        return key

    def size(self, key):
        return self.s3.head_object(Bucket=self.bucket, Key=_safe(key))["ContentLength"]

    def read_range(self, key, start, end, chunk=1024 * 1024):
        body = self.s3.get_object(Bucket=self.bucket, Key=_safe(key), Range="bytes=%d-%d" % (start, end))["Body"]
        while True:
            data = body.read(chunk)
            if not data:
                break
            yield data

    def delete_prefix(self, prefix):
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=_safe(prefix)):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})

    def delete(self, key):
        self.s3.delete_object(Bucket=self.bucket, Key=_safe(key))

    def local_copy(self, key, workdir):
        path = os.path.join(workdir, os.path.basename(key))
        with open(path, "wb") as fh:
            fh.write(self.get(key))
        return path


_store = None


def store():
    global _store
    if _store is None:
        _store = S3Storage(settings.s3_bucket) if settings.s3_bucket else LocalStorage(settings.storage_dir)
    return _store


def reset(root=None):
    global _store
    _store = LocalStorage(root) if root else None


def workdir():
    return tempfile.mkdtemp(prefix="lm-")
