from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class CriarSessaoRequest(BaseModel):
    apartamento: str

class CriarSessaoResponse(BaseModel):
    session_id: str

class EnviarMensagemRequest(BaseModel):
    texto: str

class ConfirmacaoPendenteItem(BaseModel):
    id: str
    acao: str
    detalhes: Dict[str, Any]

class MensagemResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: List[ConfirmacaoPendenteItem]

class ResponderConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool

class ReservaItem(BaseModel):
    codigo: str
    area: str
    data: str

class VisitanteItem(BaseModel):
    nome: str
    data: str
