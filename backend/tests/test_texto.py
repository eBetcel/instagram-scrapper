from agenda.texto import slugificar


def test_slugificar():
    assert slugificar("Jazz em Natal") == "jazz-em-natal"
    assert slugificar("  Música & Arte — São Paulo!! ") == "musica-arte-sao-paulo"
    assert slugificar("!!!") == "grupo"
