"""Central storage-root config. Local: data/  |  Cloud: s3://bucket/

LAKE_ROOT unset      -> "data"                    (data/bronze, data/silver, ...)
LAKE_ROOT=s3://bkt   -> "s3://bkt"                (s3://bkt/bronze, s3://bkt/silver)

S3_ENDPOINT_URL unset -> talks to AWS S3 (default).
S3_ENDPOINT_URL set   -> talks to any S3-compatible store (Cloudflare R2, MinIO, ...).
  e.g. S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com

pandas read_csv/to_csv accept both "data/..." and "s3://..." transparently once
s3fs is installed. glob and makedirs are local-only, so use lake_glob/lake_makedirs.
Values are read at CALL time so paths pick up .env loaded after this import.
"""
import os


def lake_root():
    return os.environ.get("LAKE_ROOT", "data").rstrip("/")


def is_s3():
    return lake_root().startswith("s3://")


def _s3fs():
    """One place that builds the S3 filesystem. Honors S3_ENDPOINT_URL so the
    same code hits AWS S3 (unset) or Cloudflare R2 / MinIO (set)."""
    import s3fs
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    return s3fs.S3FileSystem(
        client_kwargs={"endpoint_url": endpoint} if endpoint else {}
    )


def lake_path(*parts):
    """Join parts under the lake root; works for local and s3:// roots."""
    return "/".join([lake_root(), *[str(p).strip("/") for p in parts]])


def lake_glob(pattern):
    """Glob under the lake (local or S3). Returns full paths pandas can read."""
    if str(pattern).startswith("s3://"):
        fs = _s3fs()
        return sorted("s3://" + key for key in fs.glob(pattern[len("s3://"):]))
    import glob as _glob
    return sorted(_glob.glob(pattern))


def lake_exists(path):
    """Existence check for a single local path or s3:// key."""
    if str(path).startswith("s3://"):
        return _s3fs().exists(path)
    return os.path.exists(path)


def lake_makedirs(path):
    """Create dirs locally; no-op on S3 (object stores have no directories)."""
    if not str(path).startswith("s3://"):
        os.makedirs(path, exist_ok=True)