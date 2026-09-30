from typing import Any

from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from src.agents.main_agent import main_agent
from src.storage.repository import Repository

# Global session service for ADK runtime
session_service = InMemorySessionService()


class ADKRunnerWrapper:
    @staticmethod
    async def registrar_resultado_confirmacao(
        session_id: str,
        conf: dict[str, Any],
        confirmado: bool,
        resultado: str,
    ) -> None:
        sess = Repository.obter_sessao(session_id)
        if not sess:
            return

        adk_session = await session_service.get_session(
            app_name="aurora",
            user_id="user",
            session_id=session_id,
        )
        if not adk_session:
            adk_session = await session_service.create_session(
                app_name="aurora",
                user_id="user",
                session_id=session_id,
                state={"apartamento": sess["apartamento"]},
            )

        status = "aprovada" if confirmado else "recusada"
        nota = (
            f"A confirmação {conf['id']} foi {status}. {resultado} "
            "Se o morador fizer um novo pedido para a mesma operação, trate-o "
            "como uma nova solicitação."
        )
        event = Event(
            invocation_id=f"confirmation-{conf['id']}",
            author="assistente_principal",
            content=Content(
                role="model",
                parts=[Part.from_text(text=nota)],
            ),
        )
        await session_service.append_event(adk_session, event)

    @staticmethod
    async def processar_mensagem(session_id: str, texto_usuario: str) -> str:
        # Load session info from DB
        sess = Repository.obter_sessao(session_id)
        if not sess:
            raise ValueError("Sessão não encontrada")

        apartamento = sess["apartamento"]

        # Get or create ADK session
        try:
            adk_session = await session_service.get_session(
                app_name="aurora", user_id="user", session_id=session_id
            )
        except Exception:
            adk_session = None

        if not adk_session:
            try:
                adk_session = await session_service.create_session(
                    app_name="aurora",
                    user_id="user",
                    session_id=session_id,
                    state={"apartamento": apartamento},
                )
            except Exception:
                pass
        else:
            if hasattr(adk_session, "state"):
                adk_session.state["apartamento"] = apartamento

        # Save user message event in DB
        Repository.adicionar_evento(
            session_id, "user_message", {"texto": texto_usuario}
        )

        resposta_texto = ""
        try:
            runner = Runner(
                agent=main_agent, session_service=session_service, app_name="aurora"
            )
            user_content = Content(
                role="user", parts=[Part.from_text(text=texto_usuario)]
            )
            events = runner.run_async(
                session_id=session_id, new_message=user_content, user_id="user"
            )
            async for event in events:
                # Store event details
                event_dict = {
                    "type": getattr(event, "type", "event"),
                    "author": getattr(event, "author", None),
                }
                if hasattr(event, "content") and event.content:
                    if hasattr(event.content, "parts"):
                        parts_text = []
                        for p in event.content.parts:
                            if hasattr(p, "text") and p.text:
                                parts_text.append(p.text)
                            elif hasattr(p, "function_call") and p.function_call:
                                parts_text.append(f"call: {p.function_call.name}")
                            elif (
                                hasattr(p, "function_response") and p.function_response
                            ):
                                parts_text.append(
                                    f"response: {p.function_response.name}"
                                )
                        event_dict["content"] = " ".join(parts_text)
                    else:
                        event_dict["content"] = str(event.content)
                else:
                    event_dict["content"] = str(event)

                Repository.adicionar_evento(session_id, event_dict["type"], event_dict)

                # Check for model text response
                if (
                    hasattr(event, "content")
                    and event.content
                    and getattr(event, "role", "") == "model"
                ):
                    if hasattr(event.content, "parts"):
                        for p in event.content.parts:
                            if hasattr(p, "text") and p.text:
                                resposta_texto += p.text

            if not resposta_texto.strip():
                # If execution stopped waiting for confirmation
                pending = Repository.obter_confirmacoes_pendentes(session_id)
                if pending:
                    resposta_texto = "Sua solicitação gerou uma confirmação pendente. Por favor, responda à confirmação para prosseguir."
        except Exception as e:
            resposta_texto = f"Ocorreu um erro no processamento: {str(e)}"
            Repository.adicionar_evento(session_id, "error", str(e))

        return resposta_texto

    @staticmethod
    async def processar_confirmacao_aprovada(
        session_id: str, conf: dict[str, Any]
    ) -> str:
        sess = Repository.obter_sessao(session_id)
        apartamento = sess["apartamento"]
        acao = conf["acao"]
        detalhes = conf["detalhes"]

        res_msg = ""
        if acao == "reservar_area":
            res = Repository.criar_reserva(
                apartamento=apartamento, area=detalhes["area"], data=detalhes["data"]
            )
            if res["sucesso"]:
                res_msg = f"Confirmação recebida! Reserva da área '{detalhes['area']}' para a data {detalhes['data']} confirmada com sucesso. Código: {res['codigo']}."
            else:
                res_msg = f"Confirmação recebida, porém a reserva não pôde ser efetuada: {res['mensagem']}"

        elif acao == "autorizar_visitante":
            res = Repository.autorizar_visitante(
                apartamento=apartamento, nome=detalhes["nome"], data=detalhes["data"]
            )
            res_msg = f"Confirmação recebida! Entrada do visitante '{detalhes['nome']}' autorizada com sucesso para a data {detalhes['data']}."
        else:
            res_msg = "Confirmação processada."

        Repository.adicionar_evento(
            session_id,
            "system_confirmation",
            {"confirmado": True, "detalhes": detalhes, "resultado": res_msg},
        )
        return res_msg
