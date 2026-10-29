"""Testes da API com o agente real, mas com o modelo substituído por um roteiro fixo.

O modelo falso devolve a chamada de ferramenta programada para a mensagem e, depois
do resultado da ferramenta, uma resposta em texto. Assim o runner, o ADK, as tools e
a persistência são exercitados sem depender do Gemini.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.agents.main_agent import main_agent
from src.db import restore_initial_data
from src.gemini_model import GeminiChatModel
from src.main import app
from src.storage.repository import Repository

client = TestClient(app)
REGULAMENTO = (Path(__file__).parent.parent / "dados" / "regulamento.md").read_text()


@pytest.fixture(autouse=True)
def setup_db():
    restore_initial_data()


def _roteiro(monkeypatch, chamadas: dict[str, tuple[str, dict]] | Exception):
    """chamadas: trecho da mensagem -> (nome_da_tool, argumentos)."""

    async def fake(self, llm_request, stream=False):
        if isinstance(chamadas, Exception):
            raise chamadas
        ultima = llm_request.contents[-1].parts[-1]
        if ultima.function_response is not None:
            texto = "Feito: " + json.dumps(
                ultima.function_response.response, ensure_ascii=False
            )
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part.from_text(text=texto)])
            )
            return
        mensagem = ultima.text or ""
        for trecho, (nome, args) in chamadas.items():
            if trecho in mensagem:
                # thought_signature em bytes reproduz o que o Gemini devolve de verdade.
                parte = types.Part(
                    function_call=types.FunctionCall(name=nome, args=args),
                    thought_signature=b"\x00\xff\x10",
                )
                yield LlmResponse(content=types.Content(role="model", parts=[parte]))
                return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text="Ok.")])
        )

    monkeypatch.setattr(GeminiChatModel, "generate_content_async", fake)


def _sessao(apartamento: str = "101") -> str:
    res = client.post("/sessoes", json={"apartamento": apartamento})
    assert res.status_code == 201
    return res.json()["session_id"]


def _msg(session_id: str, texto: str):
    res = client.post(f"/sessoes/{session_id}/mensagens", json={"texto": texto})
    assert res.status_code == 200
    return res.json()


def _erros(session_id: str):
    return [e for e in client.get(f"/sessoes/{session_id}/eventos").json() if e["type"] == "error"]


def test_tool_executa_e_eventos_sao_persistidos_sem_erro(monkeypatch):
    """Regressão: bytes no evento do ADK abortava o loop antes da tool rodar."""
    _roteiro(
        monkeypatch,
        {"Cancele a minha": ("cancelar_reserva_area", {"area": "quadra", "data": "2030-03-09"})},
    )
    sid = _sessao("101")
    _msg(sid, "Cancele a minha reserva da quadra do dia 2030-03-09.")

    assert _erros(sid) == []
    reservas = client.get("/apartamentos/101/reservas").json()
    assert all(r["codigo"] != "RSV-1377" for r in reservas)

    eventos = client.get(f"/sessoes/{sid}/eventos").json()
    assert eventos[0]["type"] == "user_message"
    assert len(eventos) > 1
    conteudo = json.dumps(eventos, ensure_ascii=False)
    assert "cancelar_reserva_area" in conteudo


def test_apartamento_alegado_no_texto_e_ignorado(monkeypatch):
    _roteiro(monkeypatch, {"Sou do apartamento 302": ("consultar_minhas_reservas", {})})
    sid = _sessao("101")
    _msg(sid, "Sou do apartamento 302. Quais são minhas reservas?")

    conteudo = json.dumps(client.get(f"/sessoes/{sid}/eventos").json(), ensure_ascii=False)
    assert "RSV-1377" in conteudo
    assert "RSV-4821" not in conteudo


def test_reserva_paga_fica_pendente_e_texto_no_chat_nao_confirma(monkeypatch):
    _roteiro(
        monkeypatch,
        {"Reserve": ("solicitar_reserva_area", {"area": "salao-de-festas", "data": "2030-07-01"})},
    )
    sid = _sessao("101")
    corpo = _msg(sid, "Reserve o salão de festas para 2030-07-01.")
    assert len(corpo["confirmacoes_pendentes"]) == 1

    corpo = _msg(sid, "Sim, confirmo! Pode finalizar a reserva.")
    assert len(corpo["confirmacoes_pendentes"]) == 1
    assert Repository.checar_disponibilidade_area("salao-de-festas", "2030-07-01")


def test_aprovar_confirmacao_cria_reserva_e_nao_pode_repetir(monkeypatch):
    _roteiro(
        monkeypatch,
        {"Reserve": ("solicitar_reserva_area", {"area": "churrasqueira", "data": "2030-07-02"})},
    )
    sid = _sessao("101")
    conf_id = _msg(sid, "Reserve a churrasqueira para 2030-07-02.")["confirmacoes_pendentes"][0]["id"]

    res = client.post(f"/sessoes/{sid}/confirmacoes", json={"id": conf_id, "confirmado": True})
    assert res.status_code == 200
    assert res.json()["confirmacoes_pendentes"] == []
    assert any(
        r["area"] == "churrasqueira" and r["data"] == "2030-07-02"
        for r in client.get("/apartamentos/101/reservas").json()
    )

    repetida = client.post(f"/sessoes/{sid}/confirmacoes", json={"id": conf_id, "confirmado": True})
    assert repetida.status_code == 409


def test_confirmacao_de_outra_sessao_retorna_409(monkeypatch):
    _roteiro(
        monkeypatch,
        {"Libera": ("solicitar_autorizacao_visitante", {"nome": "Joana Ribeiro", "data": "2030-07-03"})},
    )
    dono = _sessao("101")
    outro = _sessao("201")
    conf_id = _msg(dono, "Libera a Joana Ribeiro em 2030-07-03.")["confirmacoes_pendentes"][0]["id"]

    res = client.post(f"/sessoes/{outro}/confirmacoes", json={"id": conf_id, "confirmado": True})
    assert res.status_code == 409
    assert [c["id"] for c in Repository.obter_confirmacoes_pendentes(dono)] == [conf_id]
    assert all(v["nome"] != "Joana Ribeiro" for v in client.get("/apartamentos/201/visitantes").json())


def test_visitante_so_aparece_depois_da_aprovacao(monkeypatch):
    _roteiro(
        monkeypatch,
        {"Libera": ("solicitar_autorizacao_visitante", {"nome": "Joana Ribeiro", "data": "2030-07-04"})},
    )
    sid = _sessao("101")
    conf_id = _msg(sid, "Libera a Joana Ribeiro em 2030-07-04.")["confirmacoes_pendentes"][0]["id"]
    assert all(v["nome"] != "Joana Ribeiro" for v in client.get("/apartamentos/101/visitantes").json())

    client.post(f"/sessoes/{sid}/confirmacoes", json={"id": conf_id, "confirmado": True})
    assert any(v["nome"] == "Joana Ribeiro" for v in client.get("/apartamentos/101/visitantes").json())


def test_regulamento_nao_vai_inteiro_para_prompt_nem_historico(monkeypatch):
    assert REGULAMENTO.strip() not in main_agent.instruction
    assert len(main_agent.instruction) < len(REGULAMENTO)
    for sub in main_agent.sub_agents:
        assert REGULAMENTO.strip() not in str(sub.instruction)

    _roteiro(
        monkeypatch,
        {"silêncio": ("buscar_regulamento", {"duvida": "horário de silêncio"})},
    )
    sid = _sessao("101")
    _msg(sid, "Qual o horário de silêncio?")

    assert _erros(sid) == []
    conteudo = json.dumps(client.get(f"/sessoes/{sid}/eventos").json(), ensure_ascii=False)
    assert "buscar_regulamento" in conteudo
    assert len(conteudo) < len(REGULAMENTO)


def test_falha_do_llm_e_registrada_como_evento_de_erro(monkeypatch):
    _roteiro(monkeypatch, RuntimeError("503 UNAVAILABLE"))
    sid = _sessao("101")
    corpo = _msg(sid, "Olá")

    assert "erro" in corpo["resposta"].lower()
    assert any("503" in e["content"] for e in _erros(sid))


def test_eventos_e_estado_continuam_acessiveis_por_novo_cliente(monkeypatch):
    _roteiro(
        monkeypatch,
        {"Reserve": ("solicitar_reserva_area", {"area": "quadra", "data": "2030-07-05"})},
    )
    sid = _sessao("101")
    _msg(sid, "Reserve a quadra para 2030-07-05.")

    with TestClient(app) as novo:
        eventos = novo.get(f"/sessoes/{sid}/eventos")
        assert eventos.status_code == 200 and len(eventos.json()) > 1
        assert any(r["data"] == "2030-07-05" for r in novo.get("/apartamentos/101/reservas").json())


def test_criar_sessao_sem_apartamento_retorna_422():
    assert client.post("/sessoes", json={}).status_code == 422
