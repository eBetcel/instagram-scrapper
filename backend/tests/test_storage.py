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

    c = S3Storage("http://localhost:8333", "b", "k", "s")._client
    assert c.meta.region_name == "us-east-1"
    assert c.meta.config.signature_version == "s3v4"


def test_s3_storage_from_settings_usa_o_segredo_em_texto(monkeypatch):
    from agenda.config import Settings
    from agenda.storage import S3Storage

    vistos = []
    monkeypatch.setattr(S3Storage, "__init__", lambda self, *a: vistos.append(a) or None)
    S3Storage.from_settings(Settings(
        _env_file=None, openai_modelo_extracao="x", openai_modelo_reconciliacao="y",
        s3_access_key="k", s3_secret_key="segredo-falso",
    ))
    assert vistos[0][2:] == ("k", "segredo-falso")


class _ClienteFalso:
    def __init__(self, head_codigo=None):
        self.head_codigo = head_codigo
        self.chamadas = []

    def head_bucket(self, Bucket):
        self.chamadas.append("head")
        if self.head_codigo:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": self.head_codigo}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self.chamadas.append("create")

    def put_object(self, **kw):
        self.chamadas.append("put")


def _storage(cliente):
    from agenda.storage import S3Storage

    st = S3Storage("http://localhost:8333", "b", "k", "s")
    st._client = cliente
    return st


def test_s3_storage_cria_bucket_ausente_uma_vez():
    c = _ClienteFalso(head_codigo="404")
    st = _storage(c)
    st.salvar("a", b"x", "image/jpeg")
    st.salvar("b", b"x", "image/jpeg")
    assert c.chamadas == ["head", "create", "put", "put"]


def test_s3_storage_nao_cria_bucket_existente():
    c = _ClienteFalso()
    _storage(c).salvar("a", b"x", "image/jpeg")
    assert c.chamadas == ["head", "put"]


def test_s3_storage_propaga_erro_de_acesso_no_head():
    from botocore.exceptions import ClientError

    c = _ClienteFalso(head_codigo="403")
    with pytest.raises(ClientError):
        _storage(c).salvar("a", b"x", "image/jpeg")
    assert "create" not in c.chamadas
