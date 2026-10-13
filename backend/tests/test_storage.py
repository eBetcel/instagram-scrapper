import pytest

from agenda.storage import MemoriaStorage


def test_memoria_storage_roundtrip():
    s = MemoriaStorage()
    s.salvar("a/b.jpg", b"dados", "image/jpeg")
    assert s.ler("a/b.jpg") == b"dados"


def test_memoria_storage_chave_ausente():
    with pytest.raises(KeyError):
        MemoriaStorage().ler("nada")
