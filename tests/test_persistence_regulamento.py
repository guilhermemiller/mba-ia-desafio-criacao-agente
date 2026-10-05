import asyncio

from google.adk.events import Event
from google.adk.sessions import DatabaseSessionService
from google.genai.types import Content, Part

from src.tools.regulamento_tools import buscar_regulamento


def test_adk_session_and_events_survive_service_recreation(tmp_path):
    database_path = tmp_path / "adk-sessions.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"

    async def verify_persistence():
        first_service = DatabaseSessionService(db_url=database_url)
        second_service = DatabaseSessionService(db_url=database_url)
        try:
            session = await first_service.create_session(
                app_name="persistence-test",
                user_id="test-user",
                session_id="persistent-session",
                state={"apartamento": "101"},
            )
            await first_service.append_event(
                session,
                Event(
                    invocation_id="test-invocation",
                    author="user",
                    content=Content(
                        role="user", parts=[Part.from_text(text="mensagem persistida")]
                    ),
                ),
            )

            restored = await second_service.get_session(
                app_name="persistence-test",
                user_id="test-user",
                session_id="persistent-session",
            )

            assert restored is not None
            assert restored.state["apartamento"] == "101"
            assert restored.events[-1].content.parts[0].text == "mensagem persistida"
        finally:
            await first_service.db_engine.dispose()
            await second_service.db_engine.dispose()

    asyncio.run(verify_persistence())


def test_regulamento_retorna_apenas_artigo_relevante_para_horario_da_academia():
    trecho = buscar_regulamento("Qual é o horário de funcionamento da academia?")

    assert "**Art. 29.**" in trecho
    assert "**Art. 30.**" not in trecho
    assert "## Capítulo" not in trecho


def test_regulamento_retorna_artigo_do_periodo_de_silencio():
    trecho = buscar_regulamento("Qual é o horário do período de silêncio?")

    assert "**Art. 16.**" in trecho
    assert "**Art. 15.**" not in trecho
    assert "## Capítulo" not in trecho
