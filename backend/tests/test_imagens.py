import io

import pytest
from PIL import Image

from agenda.imagens import ImagemInvalida, redimensionar


def _bytes(tamanho, modo="RGB", formato="PNG"):
    buf = io.BytesIO()
    Image.new(modo, tamanho, (200, 10, 10, 128) if modo == "RGBA" else "red").save(
        buf, format=formato
    )
    return buf.getvalue()


def _abrir(dados):
    return Image.open(io.BytesIO(dados))


def test_redimensionar_limita_lado_maior_a_1024():
    img = _abrir(redimensionar(_bytes((3000, 1500))))
    assert img.format == "JPEG"
    assert img.size == (1024, 512)


def test_redimensionar_nao_amplia():
    img = _abrir(redimensionar(_bytes((400, 300))))
    assert img.size == (400, 300)


def test_redimensionar_aceita_png_com_alpha():
    img = _abrir(redimensionar(_bytes((100, 100), modo="RGBA")))
    assert img.format == "JPEG"
    assert img.mode == "RGB"


def test_redimensionar_rejeita_bytes_invalidos():
    with pytest.raises(ImagemInvalida):
        redimensionar(b"nao e imagem")
