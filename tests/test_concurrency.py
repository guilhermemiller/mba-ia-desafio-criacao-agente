import pytest
import asyncio
import concurrent.futures
from src.db import restore_initial_data
from src.storage.repository import Repository

@pytest.fixture(autouse=True)
def setup_db():
    restore_initial_data()

def test_concurrency_atomic_reservation():
    area = "salao-de-festas"
    data = "2030-05-11"

    results = []

    def make_booking(apt):
        return Repository.criar_reserva(apartamento=apt, area=area, data=data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(make_booking, "101")
        f2 = executor.submit(make_booking, "201")
        results.append(f1.result())
        results.append(f2.result())

    successes = [r for r in results if r.get("sucesso") is True]
    failures = [r for r in results if r.get("sucesso") is False]

    # Exactly 1 booking must succeed and 1 must fail due to unique constraint
    assert len(successes) == 1
    assert len(failures) == 1

    # Verify only 1 reservation exists in DB
    res_101 = Repository.listar_reservas_apartamento("101")
    res_201 = Repository.listar_reservas_apartamento("201")

    total_bookings = [r for r in res_101 + res_201 if r["area"] == area and r["data"] == data]
    assert len(total_bookings) == 1


def test_codigo_de_reserva_repetido_e_sorteado_de_novo(monkeypatch):
    from types import SimpleNamespace

    import src.storage.repository as repo

    # A segunda reserva sorteia RSV-AAAA (já usado) e deve tentar de novo até RSV-BBBB.
    sequencia = iter(["aaaa" + "0" * 28, "aaaa" + "1" * 28, "bbbb" + "0" * 28])
    monkeypatch.setattr(repo.uuid, "uuid4", lambda: SimpleNamespace(hex=next(sequencia)))

    r1 = Repository.criar_reserva("101", "salao-de-festas", "2030-08-01")
    r2 = Repository.criar_reserva("201", "salao-de-festas", "2030-08-02")

    assert r1["sucesso"] and r1["codigo"] == "RSV-AAAA"
    assert r2["sucesso"] and r2["codigo"] == "RSV-BBBB"
