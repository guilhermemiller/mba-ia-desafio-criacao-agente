"""Disputa simultânea pela API (Garantia 5) e reinício real do servidor (Garantia 3)."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from src.db import restore_initial_data
from src.main import app
from src.storage.repository import Repository

RAIZ = Path(__file__).parent.parent


def test_duas_aprovacoes_simultaneas_geram_uma_unica_reserva():
    restore_initial_data()
    area, data = "salao-de-festas", "2030-05-11"

    async def disputar():
        # Um único event loop, como no uvicorn: o serviço de sessões do ADK fica preso ao loop.
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://api") as api:
            disputas = []
            for apartamento in ("101", "201"):
                sid = (await api.post("/sessoes", json={"apartamento": apartamento})).json()["session_id"]
                conf = Repository.criar_confirmacao_pendente(
                    sid, "reservar_area", {"area": area, "data": data, "taxa": 150.0}
                )
                disputas.append((sid, conf))

            respostas = await asyncio.gather(
                *[
                    api.post(f"/sessoes/{sid}/confirmacoes", json={"id": conf, "confirmado": True})
                    for sid, conf in disputas
                ]
            )
            reservas = [
                r
                for apt in ("101", "201")
                for r in (await api.get(f"/apartamentos/{apt}/reservas")).json()
                if r["area"] == area and r["data"] == data
            ]
            return [r.status_code for r in respostas], reservas

    status, reservas = asyncio.run(disputar())

    assert status == [200, 200]
    assert len(reservas) == 1


# --------------------------------------------------------------------------
# Reinício real: dois processos uvicorn em sequência sobre o mesmo banco
# --------------------------------------------------------------------------


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Servidor:
    def __init__(self, banco: Path, porta: int, restaurar: bool):
        env = {**os.environ, "DATABASE_PATH": str(banco), "PYTHONPATH": str(RAIZ)}
        args = [sys.executable, str(RAIZ / "tests" / "_servidor_falso.py"), str(porta)]
        if restaurar:
            args.append("--restaurar")
        self.base = f"http://127.0.0.1:{porta}"
        self.proc = subprocess.Popen(
            args, cwd=RAIZ, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        limite = time.time() + 60
        while time.time() < limite:
            if self.proc.poll() is not None:
                raise RuntimeError(f"servidor encerrou: {self.proc.stdout.read()}")
            try:
                httpx.get(f"{self.base}/apartamentos/101/reservas", timeout=1)
                return
            except httpx.HTTPError:
                time.sleep(0.3)
        self.parar()
        raise RuntimeError("servidor não subiu em 60s")

    def parar(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def get(self, caminho):
        return httpx.get(f"{self.base}{caminho}", timeout=30)

    def post(self, caminho, corpo):
        return httpx.post(f"{self.base}{caminho}", json=corpo, timeout=120)


def _codigos(servidor: _Servidor) -> set[str]:
    return {
        r["codigo"]
        for apt in ("101", "201", "302")
        for r in servidor.get(f"/apartamentos/{apt}/reservas").json()
    }


def test_estado_sobrevive_ao_reinicio_da_api(tmp_path):
    banco = tmp_path / "reinicio.db"
    porta = _porta_livre()

    antes = _Servidor(banco, porta, restaurar=True)
    try:
        sid = antes.post("/sessoes", {"apartamento": "101"}).json()["session_id"]
        antes.post(f"/sessoes/{sid}/mensagens", {"texto": "Reserve a quadra para 2030-09-01."})
        antes.post(f"/sessoes/{sid}/mensagens", {"texto": "Cancele a minha reserva da quadra."})
        pendente = antes.post(
            f"/sessoes/{sid}/mensagens", {"texto": "Libera a Joana Ribeiro em 2030-09-03."}
        ).json()["confirmacoes_pendentes"]
        assert len(pendente) == 1
        aprovada = antes.post(
            f"/sessoes/{sid}/confirmacoes", {"id": pendente[0]["id"], "confirmado": True}
        )
        assert aprovada.status_code == 200

        eventos_antes = antes.get(f"/sessoes/{sid}/eventos").json()
        reservas_antes = antes.get("/apartamentos/101/reservas").json()
        codigos_antes = _codigos(antes)
    finally:
        antes.parar()

    assert any(r["data"] == "2030-09-01" for r in reservas_antes)
    assert all(r["codigo"] != "RSV-1377" for r in reservas_antes)
    assert not [e for e in eventos_antes if e["type"] == "error"]

    depois = _Servidor(banco, _porta_livre(), restaurar=False)
    try:
        # Mesma sessão, mesmos eventos (os novos só podem vir depois).
        eventos_depois = depois.get(f"/sessoes/{sid}/eventos")
        assert eventos_depois.status_code == 200
        assert eventos_depois.json() == eventos_antes

        # Reservas, cancelamento e visitante continuam nas rotas de verificação.
        assert depois.get("/apartamentos/101/reservas").json() == reservas_antes
        assert any(
            v["nome"] == "Joana Ribeiro" for v in depois.get("/apartamentos/101/visitantes").json()
        )

        # A sessão aceita novas mensagens e o código novo não repete nenhum anterior.
        nova = depois.post(f"/sessoes/{sid}/mensagens", {"texto": "Reserve outra quadra."})
        assert nova.status_code == 200
        eventos_final = depois.get(f"/sessoes/{sid}/eventos").json()
        assert eventos_final[: len(eventos_antes)] == eventos_antes
        assert len(eventos_final) > len(eventos_antes)
        assert not [e for e in eventos_final if e["type"] == "error"]

        novos = _codigos(depois) - codigos_antes
        assert len(novos) == 1
    finally:
        depois.parar()
