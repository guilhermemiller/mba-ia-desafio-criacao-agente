"""Testes das tools de reservas e visitantes, sem LLM."""

import uuid
from types import SimpleNamespace

import pytest

from src.db import restore_initial_data
from src.storage.repository import Repository
from src.tools.reservas_tools import (
    cancelar_reserva_area,
    checar_disponibilidade_area,
    consultar_minhas_reservas,
    solicitar_reserva_area,
)
from src.tools.visitantes_tools import (
    consultar_meus_visitantes,
    solicitar_autorizacao_visitante,
)


@pytest.fixture(autouse=True)
def setup_db():
    restore_initial_data()


def _ctx(apartamento: str):
    session_id = f"sess-tools-{apartamento}-{uuid.uuid4().hex[:8]}"
    Repository.criar_sessao(session_id, apartamento)
    return SimpleNamespace(session_id=session_id, state={"apartamento": apartamento})


def test_consultar_minhas_reservas_lista_apenas_o_proprio_apartamento():
    resultado = consultar_minhas_reservas(_ctx("101"))
    assert "RSV-1377" in resultado
    assert "RSV-4821" not in resultado
    assert "RSV-2950" not in resultado


def test_consultar_minhas_reservas_sem_reservas():
    resultado = consultar_minhas_reservas(_ctx("999"))
    assert "não possui reservas" in resultado


def test_checar_disponibilidade_nao_revela_quem_reservou():
    ocupada = checar_disponibilidade_area("salao-de-festas", "2030-03-16")
    assert "OCUPADA" in ocupada
    assert "302" not in ocupada and "RSV-4821" not in ocupada

    livre = checar_disponibilidade_area("salao-de-festas", "2030-12-01")
    assert "LIVRE" in livre


def test_apartamento_vem_da_sessao_e_nao_do_texto():
    # A tool não recebe apartamento como argumento: só o contexto da sessão vale.
    resultado = consultar_minhas_reservas(_ctx("101"))
    assert "RSV-4821" not in resultado


def test_apartamento_resolvido_pelo_banco_quando_estado_vazio():
    session_id = f"sess-sem-estado-{uuid.uuid4().hex[:8]}"
    Repository.criar_sessao(session_id, "201")
    ctx = SimpleNamespace(session_id=session_id, state={})
    assert "RSV-2950" in consultar_minhas_reservas(ctx)


def test_sem_sessao_retorna_erro():
    assert "Erro" in consultar_minhas_reservas(None)
    assert "Erro" in solicitar_reserva_area("quadra", "2030-06-01", None)
    assert "Erro" in cancelar_reserva_area("quadra", "2030-03-09", None)


def test_reserva_gratuita_e_imediata():
    ctx = _ctx("101")
    resultado = solicitar_reserva_area("quadra", "2030-06-01", ctx)
    assert "confirmada" in resultado
    assert any(
        r["area"] == "quadra" and r["data"] == "2030-06-01"
        for r in Repository.listar_reservas_apartamento("101")
    )
    assert Repository.obter_confirmacoes_pendentes(ctx.session_id) == []


def test_reserva_paga_gera_confirmacao_e_nao_reserva():
    ctx = _ctx("101")
    resultado = solicitar_reserva_area("churrasqueira", "2030-06-02", ctx)
    assert "confirmação pendente" in resultado

    pendentes = Repository.obter_confirmacoes_pendentes(ctx.session_id)
    assert len(pendentes) == 1
    assert pendentes[0]["acao"] == "reservar_area"
    assert pendentes[0]["detalhes"]["taxa"] == 80.0
    assert Repository.checar_disponibilidade_area("churrasqueira", "2030-06-02")


def test_reserva_em_data_ocupada_e_recusada():
    ctx = _ctx("101")
    resultado = solicitar_reserva_area("salao-de-festas", "2030-03-16", ctx)
    assert "ocupada" in resultado
    assert Repository.obter_confirmacoes_pendentes(ctx.session_id) == []


def test_area_invalida():
    resultado = solicitar_reserva_area("piscina", "2030-06-01", _ctx("101"))
    assert "inválida" in resultado


def test_cancelar_reserva_inexistente():
    resultado = cancelar_reserva_area("quadra", "2030-11-11", _ctx("101"))
    assert "Nenhuma reserva encontrada" in resultado


def test_cancelar_reserva_de_outro_apartamento_nao_remove():
    resultado = cancelar_reserva_area("salao-de-festas", "2030-03-16", _ctx("101"))
    assert "Nenhuma reserva encontrada" in resultado
    assert any(
        r["codigo"] == "RSV-4821" for r in Repository.listar_reservas_apartamento("302")
    )


def test_cancelar_reserva_propria():
    resultado = cancelar_reserva_area("quadra", "2030-03-09", _ctx("101"))
    assert "RSV-1377" in resultado and "cancelada" in resultado
    assert Repository.checar_disponibilidade_area("quadra", "2030-03-09")


def test_consultar_meus_visitantes_isola_apartamentos():
    resultado = consultar_meus_visitantes(_ctx("302"))
    assert "Marina Duarte" in resultado
    assert "Marina Duarte" not in consultar_meus_visitantes(_ctx("101"))


def test_autorizar_visitante_so_cria_confirmacao():
    ctx = _ctx("101")
    resultado = solicitar_autorizacao_visitante("Joana Ribeiro", "2030-04-21", ctx)
    assert "confirmação" in resultado

    pendentes = Repository.obter_confirmacoes_pendentes(ctx.session_id)
    assert [p["acao"] for p in pendentes] == ["autorizar_visitante"]
    visitantes = Repository.listar_visitantes_apartamento("101")
    assert all(v["nome"] != "Joana Ribeiro" for v in visitantes)
