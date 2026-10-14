"""Semeia o banco agenda_e2e: um perfil já coletado com um evento daqui a 2 dias às 21h
e dois convites (gravados em .convites.json para o Playwright)."""

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agenda.api.seguranca import criar_convite
from agenda.config import ConfigBanco
from agenda.models import Evento, EventoFonte, Perfil, Post

FUSO = ZoneInfo("America/Sao_Paulo")
agora = datetime.now(UTC)
dia = agora.astimezone(FUSO).date() + timedelta(days=2)

with Session(create_engine(ConfigBanco().database_url)) as s:
    perfil = Perfil(username="casa_e2e", ultima_coleta_em=agora)
    s.add(perfil)
    s.flush()
    post = Post(perfil_id=perfil.id, shortcode="E2E1", status="reconciliado", imagens=[], publicado_em=agora)
    evento = Evento(titulo="Show de Teste E2E", inicio=datetime.combine(dia, time(21), FUSO),
                    hora_definida=True, categoria="show", local_nome="Casa E2E", cidade="Natal")
    s.add_all([post, evento])
    s.flush()
    s.add(EventoFonte(evento_id=evento.id, post_id=post.id, decisao="novo"))
    convites = [criar_convite(s, usos=1, dias=1, agora=agora) for _ in range(2)]
    s.commit()

Path(__file__).with_name(".convites.json").write_text(json.dumps(convites))
print("agenda_e2e semeado:", ", ".join(convites))
