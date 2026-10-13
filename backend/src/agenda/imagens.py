import io

from PIL import Image, ImageOps, UnidentifiedImageError


class ImagemInvalida(ValueError):
    """Bytes que não puderam ser decodificados como imagem."""


def redimensionar(dados: bytes, lado_max: int = 1024) -> bytes:
    """Devolve JPEG (qualidade 85) com o lado maior limitado a `lado_max`.

    Mantém a proporção e não amplia imagens menores.
    """
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImagemInvalida(str(e)) from e

    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        fundo = Image.new("RGB", rgba.size, (255, 255, 255))
        fundo.paste(rgba, mask=rgba.getchannel("A"))
        img = fundo
    elif img.mode != "RGB":
        img = img.convert("RGB")

    maior = max(img.size)
    if maior > lado_max:
        escala = lado_max / maior
        novo = (max(1, round(img.width * escala)), max(1, round(img.height * escala)))
        img = img.resize(novo, Image.Resampling.LANCZOS)

    saida = io.BytesIO()
    img.save(saida, format="JPEG", quality=85)
    return saida.getvalue()
