from io import BytesIO

import pytest

from app.core.errors import RelayviaError
from app.infrastructure.artifact_storage.s3 import S3ArtifactStorage


class FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)


def test_s3_storage_uses_shared_object_keys_and_streams_content():
    client = FakeS3Client()
    storage = S3ArtifactStorage(bucket="relayvia", prefix="runs", client=client)
    assert storage.save_bytes("artifact-1", b"report") == 6
    assert client.objects[("relayvia", "runs/artifact-1")] == b"report"
    assert storage.open("artifact-1").read() == b"report"
    assert storage.exists("artifact-1") is True


def test_s3_storage_rejects_path_traversal_keys():
    storage = S3ArtifactStorage(bucket="relayvia", client=FakeS3Client())
    with pytest.raises(RelayviaError) as error:
        storage.save_bytes("../outside", b"no")
    assert error.value.code == "INVALID_ARTIFACT_KEY"
