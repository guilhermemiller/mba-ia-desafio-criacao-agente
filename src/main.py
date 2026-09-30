import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from src.adk_runner import ADKRunnerWrapper
from src.db import init_db
from src.models import (
    ConfirmacaoPendenteItem,
    CriarSessaoRequest,
    CriarSessaoResponse,
    EnviarMensagemRequest,
    MensagemResponse,
    ResponderConfirmacaoRequest,
)
from src.storage.repository import Repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Residencial Aurora Virtual Assistant API", version="1.0.0", lifespan=lifespan
)

# -------------------------------------------------------------------
# Rotas de Sessão e Conversa
# -------------------------------------------------------------------


@app.post(
    "/sessoes", status_code=status.HTTP_201_CREATED, response_model=CriarSessaoResponse
)
async def criar_sessao(req: CriarSessaoRequest):
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    Repository.criar_sessao(session_id, req.apartamento)
    return CriarSessaoResponse(session_id=session_id)


@app.post("/sessoes/{session_id}/mensagens", response_model=MensagemResponse)
async def enviar_mensagem(session_id: str, req: EnviarMensagemRequest):
    sess = Repository.obter_sessao(session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada"
        )

    resposta = await ADKRunnerWrapper.processar_mensagem(session_id, req.texto)

    # Obter confirmações pendentes
    pending_db = Repository.obter_confirmacoes_pendentes(session_id)
    confirmacoes = [
        ConfirmacaoPendenteItem(id=p["id"], acao=p["acao"], detalhes=p["detalhes"])
        for p in pending_db
    ]

    return MensagemResponse(resposta=resposta, confirmacoes_pendentes=confirmacoes)


@app.post("/sessoes/{session_id}/confirmacoes", response_model=MensagemResponse)
async def responder_confirmacao(session_id: str, req: ResponderConfirmacaoRequest):
    sess = Repository.obter_sessao(session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada"
        )

    conf = Repository.obter_confirmacao(session_id, req.id)
    if not conf or conf["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não existe confirmação pendente com esse id nesta sessão",
        )

    if req.confirmado:
        Repository.atualizar_status_confirmacao(req.id, "approved")
        resposta = await ADKRunnerWrapper.processar_confirmacao_aprovada(
            session_id, conf
        )
    else:
        Repository.atualizar_status_confirmacao(req.id, "rejected")
        Repository.adicionar_evento(
            session_id,
            "system_confirmation",
            {"confirmado": False, "detalhes": conf["detalhes"]},
        )
        resposta = "Confirmação negada pelo morador. Nenhuma ação foi executada."

    await ADKRunnerWrapper.registrar_resultado_confirmacao(
        session_id, conf, req.confirmado, resposta
    )

    pending_db = Repository.obter_confirmacoes_pendentes(session_id)
    confirmacoes = [
        ConfirmacaoPendenteItem(id=p["id"], acao=p["acao"], detalhes=p["detalhes"])
        for p in pending_db
    ]

    return MensagemResponse(resposta=resposta, confirmacoes_pendentes=confirmacoes)


@app.get("/sessoes/{session_id}/eventos")
async def ver_eventos(session_id: str):
    sess = Repository.obter_sessao(session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada"
        )

    eventos = Repository.obter_eventos(session_id)
    return eventos


# -------------------------------------------------------------------
# Rotas de Verificação Direta
# -------------------------------------------------------------------


@app.get("/apartamentos/{apartamento}/reservas")
async def ver_reservas_apartamento(apartamento: str):
    reservas = Repository.listar_reservas_apartamento(apartamento)
    return reservas


@app.get("/apartamentos/{apartamento}/visitantes")
async def ver_visitantes_apartamento(apartamento: str):
    visitantes = Repository.listar_visitantes_apartamento(apartamento)
    return visitantes


if __name__ == "__main__":
    import uvicorn

    from src.config import PORT

    uvicorn.run("src.main:app", host="0.0.0.0", port=PORT, reload=True)
