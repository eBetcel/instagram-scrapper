from agenda.texto import slugificar


def test_slugificar():
    assert slugificar("Jazz em Natal") == "jazz-em-natal"
    assert slugificar("  Música & Arte — São Paulo!! ") == "musica-arte-sao-paulo"
    assert slugificar("!!!") == "grupo"


def test_normalizar_username():
    from agenda.texto import normalizar_username

    assert normalizar_username("  @Casa.Azul_SP ") == "casa.azul_sp"
    assert normalizar_username("nome inválido!") is None
    assert normalizar_username("@") is None
    assert normalizar_username("a" * 31) is None
