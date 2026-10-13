from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from agenda.config import Settings


class Storage(Protocol):
    def salvar(self, chave: str, dados: bytes, content_type: str) -> None: ...

    def ler(self, chave: str) -> bytes: ...


class MemoriaStorage:
    """Storage em dicionário, para testes. `ler` de chave ausente levanta KeyError."""

    def __init__(self) -> None:
        self._objetos: dict[str, tuple[bytes, str]] = {}

    def salvar(self, chave: str, dados: bytes, content_type: str) -> None:
        self._objetos[chave] = (dados, content_type)

    def ler(self, chave: str) -> bytes:
        return self._objetos[chave][0]


class S3Storage:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",  # MinIO ignora a região, mas o boto3 exige uma
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Storage":
        return cls(
            settings.s3_endpoint,
            settings.s3_bucket,
            settings.s3_access_key,
            settings.s3_secret_key,
        )

    def salvar(self, chave: str, dados: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=chave, Body=dados, ContentType=content_type
        )

    def ler(self, chave: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=chave)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise KeyError(chave) from e
            raise
        return resp["Body"].read()
