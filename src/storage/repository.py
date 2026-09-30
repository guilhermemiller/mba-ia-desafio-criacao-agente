import sqlite3
import json
import uuid
from typing import List, Dict, Any, Optional
from src.db import get_db_connection

class Repository:
    @staticmethod
    def criar_sessao(session_id: str, apartamento: str):
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO sessoes (session_id, apartamento) VALUES (?, ?)",
                    (session_id, apartamento)
                )
        finally:
            conn.close()

    @staticmethod
    def obter_sessao(session_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT session_id, apartamento, created_at FROM sessoes WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    @staticmethod
    def adicionar_evento(session_id: str, evento_type: str, content: Any):
        conn = get_db_connection()
        try:
            with conn:
                content_str = json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content
                conn.execute(
                    "INSERT INTO eventos (session_id, type, content) VALUES (?, ?, ?)",
                    (session_id, evento_type, content_str)
                )
        finally:
            conn.close()

    @staticmethod
    def obter_eventos(session_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, session_id, type, content, created_at FROM eventos WHERE session_id = ? ORDER BY id ASC", (session_id,))
            rows = cursor.fetchall()
            eventos = []
            for r in rows:
                d = dict(r)
                try:
                    d["content"] = json.loads(d["content"])
                except Exception:
                    pass
                eventos.append(d)
            return eventos
        finally:
            conn.close()

    @staticmethod
    def criar_confirmacao_pendente(session_id: str, acao: str, detalhes: Dict[str, Any]) -> str:
        conf_id = f"conf-{uuid.uuid4().hex[:8]}"
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO confirmacoes (id, session_id, acao, detalhes, status) VALUES (?, ?, ?, ?, 'pending')",
                    (conf_id, session_id, acao, json.dumps(detalhes, ensure_ascii=False))
                )
            return conf_id
        finally:
            conn.close()

    @staticmethod
    def obter_confirmacoes_pendentes(session_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, acao, detalhes FROM confirmacoes WHERE session_id = ? AND status = 'pending'", (session_id,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "acao": r["acao"],
                    "detalhes": json.loads(r["detalhes"])
                })
            return result
        finally:
            conn.close()

    @staticmethod
    def obter_confirmacao(session_id: str, conf_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, session_id, acao, detalhes, status FROM confirmacoes WHERE session_id = ? AND id = ?", (session_id, conf_id))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["detalhes"] = json.loads(d["detalhes"])
                return d
            return None
        finally:
            conn.close()

    @staticmethod
    def atualizar_status_confirmacao(conf_id: str, status: str):
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("UPDATE confirmacoes SET status = ? WHERE id = ?", (status, conf_id))
        finally:
            conn.close()

    @staticmethod
    def listar_reservas_apartamento(apartamento: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT codigo, area, data FROM reservas WHERE apartamento = ? ORDER BY data ASC", (apartamento,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def checar_disponibilidade_area(area: str, data: str) -> bool:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM reservas WHERE area = ? AND data = ?", (area, data))
            row = cursor.fetchone()
            return row is None
        finally:
            conn.close()

    @staticmethod
    def criar_reserva(apartamento: str, area: str, data: str) -> Dict[str, Any]:
        """Garantia 5: atomic transaction enforcing UNIQUE(area, data)."""
        conn = get_db_connection()
        codigo = f"RSV-{uuid.uuid4().hex[:4].upper()}"
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE;")
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM reservas WHERE area = ? AND data = ?", (area, data))
                if cursor.fetchone() is not None:
                    raise ValueError(f"A área '{area}' já está reservada para a data {data}.")
                conn.execute(
                    "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                    (codigo, apartamento, area, data)
                )
            return {"sucesso": True, "codigo": codigo, "area": area, "data": data}
        except sqlite3.IntegrityError:
            return {"sucesso": False, "mensagem": f"A área '{area}' já possui uma reserva ativa para a data {data}."}
        except ValueError as ve:
            return {"sucesso": False, "mensagem": str(ve)}
        finally:
            conn.close()

    @staticmethod
    def cancelar_reserva(apartamento: str, area: str, data: str) -> Dict[str, Any]:
        """Garantia 2:Morador only cancels own apartment's reservation."""
        conn = get_db_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT codigo FROM reservas WHERE apartamento = ? AND area = ? AND data = ?", (apartamento, area, data))
                row = cursor.fetchone()
                if not row:
                    return {"sucesso": False, "mensagem": "Nenhuma reserva encontrada para cancelamento neste apartamento para esta área e data."}
                codigo = row["codigo"]
                conn.execute("DELETE FROM reservas WHERE codigo = ?", (codigo,))
            return {"sucesso": True, "mensagem": f"Reserva {codigo} cancelada com sucesso."}
        finally:
            conn.close()

    @staticmethod
    def listar_visitantes_apartamento(apartamento: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data ASC", (apartamento,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def autorizar_visitante(apartamento: str, nome: str, data: str) -> Dict[str, Any]:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
                    (apartamento, nome, data)
                )
            return {"sucesso": True, "nome": nome, "data": data}
        finally:
            conn.close()
