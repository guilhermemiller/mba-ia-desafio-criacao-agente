import json

AREAS_FEE_MAP = {
    "salao-de-festas": 150.0,
    "churrasqueira": 80.0,
    "quadra": 0.0
}

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

def consultar_minhas_reservas(tool_context) -> str:
    """Consulta as reservas do apartamento do morador logado na sessão."""
    from src.storage.repository import Repository
    apartamento, _ = _obter_apartamento_e_sessao(tool_context)
    if not apartamento:
        return "Erro: Apartamento não identificado na sessão."

    reservas = Repository.listar_reservas_apartamento(apartamento)
    if not reservas:
        return f"O apartamento {apartamento} não possui reservas ativas."
    return json.dumps(reservas, ensure_ascii=False)

def checar_disponibilidade_area(area: str, data: str, tool_context=None) -> str:
    """Checa se uma área comum está livre para reserva em uma determinada data (AAAA-MM-DD).

    ATENÇÃO: Retorna APENAS se a área está livre ou ocupada. Nunca revela quem reservou.
    """
    from src.storage.repository import Repository
    area_id = area.lower().strip()
    livre = Repository.checar_disponibilidade_area(area_id, data)
    if livre:
        return f"A área '{area_id}' está LIVRE para a data {data}."
    else:
        return f"A área '{area_id}' está OCUPADA para a data {data}."

def solicitar_reserva_area(area: str, data: str, tool_context) -> str:
    """Solicita a reserva de uma área comum para o apartamento do morador.

    - Áreas com taxa (salão de festas, churrasqueira) criam confirmação pendente.
    - Áreas sem taxa (quadra) efetuam a reserva imediatamente.
    """
    from src.storage.repository import Repository
    apartamento, session_id = _obter_apartamento_e_sessao(tool_context)

    if not apartamento or not session_id:
        return "Erro: Sessão ou apartamento não identificados."

    area_id = area.lower().strip()
    if area_id not in AREAS_FEE_MAP:
        return f"Área '{area_id}' inválida. Áreas disponíveis: salao-de-festas, churrasqueira, quadra."

    # Check current availability
    if not Repository.checar_disponibilidade_area(area_id, data):
        return f"A área '{area_id}' já está ocupada na data {data}."

    taxa = AREAS_FEE_MAP[area_id]

    if taxa > 0:
        # Garantia 1: Chargeable area requires confirmation via API route
        conf_id = Repository.criar_confirmacao_pendente(
            session_id=session_id,
            acao="reservar_area",
            detalhes={"area": area_id, "data": data, "taxa": taxa}
        )
        return f"Sua solicitação de reserva para '{area_id}' na data {data} gera uma taxa de R$ {taxa:.2f}. Foi gerada a confirmação pendente '{conf_id}'. Por favor, confirme a operação para concluir a reserva."
    else:
        # Fee is 0 (e.g. quadra) -> Immediate reservation
        res = Repository.criar_reserva(apartamento=apartamento, area=area_id, data=data)
        if res["sucesso"]:
            return f"Reserva da área '{area_id}' confirmada com sucesso para a data {data}! Código: {res['codigo']}."
        else:
            return res["mensagem"]

def cancelar_reserva_area(area: str, data: str, tool_context) -> str:
    """Cancela uma reserva do próprio apartamento do morador, sem necessidade de confirmação pendente."""
    from src.storage.repository import Repository
    apartamento, _ = _obter_apartamento_e_sessao(tool_context)
    if not apartamento:
        return "Erro: Apartamento não identificado na sessão."

    area_id = area.lower().strip()
    res = Repository.cancelar_reserva(apartamento=apartamento, area=area_id, data=data)
    return res["mensagem"]
