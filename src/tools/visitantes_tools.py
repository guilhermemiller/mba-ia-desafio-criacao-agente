import json

def _obter_apartamento_e_sessao(tool_context) -> tuple[str | None, str | None]:
    apartamento = None
    session_id = None
    if tool_context:
        if hasattr(tool_context, "session_id") and tool_context.session_id:
            session_id = tool_context.session_id

        session_obj = getattr(tool_context, "session", None)
        if not session_id and session_obj is not None:
            session_id = getattr(session_obj, "id", None)

        state_obj = getattr(tool_context, "state", None)
        if state_obj is not None:
            if hasattr(state_obj, "get"):
                apartamento = state_obj.get("apartamento")
            elif isinstance(state_obj, dict):
                apartamento = state_obj.get("apartamento")

    if not apartamento and session_id:
        from src.storage.repository import Repository
        sess = Repository.obter_sessao(session_id)
        if sess:
            apartamento = sess["apartamento"]

    return apartamento, session_id

def consultar_meus_visitantes(tool_context) -> str:
    """Consulta a lista de visitantes autorizados para o apartamento do morador logado."""
    from src.storage.repository import Repository
    apartamento, _ = _obter_apartamento_e_sessao(tool_context)
    if not apartamento:
        return "Erro: Apartamento não identificado na sessão."

    visitantes = Repository.listar_visitantes_apartamento(apartamento)
    if not visitantes:
        return f"O apartamento {apartamento} não possui autorizações de visitantes cadastradas."
    return json.dumps(visitantes, ensure_ascii=False)

def solicitar_autorizacao_visitante(nome: str, data: str, tool_context) -> str:
    """Solicita a autorização de entrada de um visitante na data especificada (AAAA-MM-DD).

    Garantia 1: Autorizar visitante sempre exige confirmação pendente via rota de confirmações.
    """
    from src.storage.repository import Repository
    apartamento, session_id = _obter_apartamento_e_sessao(tool_context)

    if not apartamento or not session_id:
        return "Erro: Sessão ou apartamento não identificados."

    conf_id = Repository.criar_confirmacao_pendente(
        session_id=session_id,
        acao="autorizar_visitante",
        detalhes={"nome": nome, "data": data}
    )
    return f"A autorização de entrada para o visitante '{nome}' no dia {data} exige sua confirmação. Foi gerada a confirmação pendente '{conf_id}'. Por favor, responda à confirmação no sistema para liberar a entrada."
