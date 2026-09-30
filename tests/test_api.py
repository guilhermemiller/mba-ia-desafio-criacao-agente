import asyncio

import pytest
from fastapi.testclient import TestClient

from src.adk_runner import session_service
from src.db import restore_initial_data
from src.main import app
from src.storage.repository import Repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    restore_initial_data()


def test_criar_sessao():
    response = client.post("/sessoes", json={"apartamento": "101"})
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data


def test_rotas_verificacao_iniciais():
    res_reservas = client.get("/apartamentos/101/reservas")
    assert res_reservas.status_code == 200
    reservas = res_reservas.json()
    assert any(r["codigo"] == "RSV-1377" for r in reservas)

    res_vis = client.get("/apartamentos/302/visitantes")
    assert res_vis.status_code == 200
    visitantes = res_vis.json()
    assert any(v["nome"] == "Marina Duarte" for v in visitantes)


def test_confirmacao_inexistente_retorna_409():
    res_sess = client.post("/sessoes", json={"apartamento": "101"})
    session_id = res_sess.json()["session_id"]

    res_conf = client.post(
        f"/sessoes/{session_id}/confirmacoes",
        json={"id": "id-inexistente", "confirmado": True},
    )
    assert res_conf.status_code == 409


def test_sessao_inexistente_retorna_404():
    res = client.get("/sessoes/sessao-inexistente/eventos")
    assert res.status_code == 404


def test_confirmacao_recusada_e_registrada_no_historico_adk():
    res_sess = client.post("/sessoes", json={"apartamento": "101"})
    session_id = res_sess.json()["session_id"]
    confirmation_id = Repository.criar_confirmacao_pendente(
        session_id,
        "reservar_area",
        {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0},
    )

    response = client.post(
        f"/sessoes/{session_id}/confirmacoes",
        json={"id": confirmation_id, "confirmado": False},
    )

    assert response.status_code == 200
    adk_session = asyncio.run(
        session_service.get_session(
            app_name="aurora", user_id="user", session_id=session_id
        )
    )
    assert adk_session is not None
    assert any(
        event.author == "assistente_principal"
        and event.content
        and any(
            part.text and "foi recusada" in part.text
            for part in event.content.parts or []
        )
        for event in adk_session.events
    )
