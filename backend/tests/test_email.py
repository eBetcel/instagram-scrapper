from agenda.config import ConfigApi
from agenda.email import FakeEnviador, SmtpEnviador


def test_fake_enviador_guarda():
    f = FakeEnviador()
    f.enviar("a@x.com", "Assunto", "corpo")
    assert f.enviados == [("a@x.com", "Assunto", "corpo")]


def test_smtp_enviador_monta_mensagem(monkeypatch):
    enviadas, conexoes = [], []

    class SMTPFalso:
        def __init__(self, host, porta, timeout=None):
            conexoes.append((host, porta))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            conexoes.append("tls")

        def login(self, u, p):
            conexoes.append(("login", u))

        def send_message(self, msg):
            enviadas.append(msg)

    monkeypatch.setattr("agenda.email.smtplib.SMTP", SMTPFalso)
    # Testa os padrões: nem o .env local nem SMTP_* do ambiente podem vazar para cá.
    for var in ("SMTP_USUARIO", "SMTP_SENHA", "SMTP_TLS"):
        monkeypatch.delenv(var, raising=False)
    cfg = ConfigApi(_env_file=None, smtp_host="smtp.x", smtp_porta=2525, email_remetente="agenda@x.com")
    SmtpEnviador(cfg).enviar("b@x.com", "Seu link", "texto do link")
    [msg] = enviadas
    assert (msg["From"], msg["To"], msg["Subject"]) == ("agenda@x.com", "b@x.com", "Seu link")
    assert "texto do link" in msg.get_content()
    assert conexoes == [("smtp.x", 2525)]  # sem TLS nem login por padrão
