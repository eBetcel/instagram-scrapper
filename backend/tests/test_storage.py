import pytest

from agenda.storage import MemoriaStorage


def test_memoria_storage_roundtrip():
    s = MemoriaStorage()
    s.salvar("a/b.jpg", b"dados", "image/jpeg")
    assert s.ler("a/b.jpg") == b"dados"


def test_memoria_storage_chave_ausente():
    with pytest.raises(KeyError):
        MemoriaStorage().ler("nada")


def test_s3_storage_configura_regiao_e_assinatura_v4():
    from agenda.storage import S3Storage

    c = S3Storage("http://localhost:9000", "b", "k", "s")._client
    assert c.meta.region_name == "us-east-1"
    assert c.meta.config.signature_version == "s3v4"
