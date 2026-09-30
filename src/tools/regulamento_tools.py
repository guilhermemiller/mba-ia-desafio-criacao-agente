import json
import re
from pathlib import Path

REGULAMENTO_PATH = Path(__file__).parent.parent.parent / "dados" / "regulamento.md"

def buscar_regulamento(duvida: str) -> str:
    """Busca trechos do regulamento interno do condomínio relacionados à dúvida do morador.

    Args:
        duvida: Texto com a dúvida ou palavra-chave (ex: 'piscina', 'horario academia', 'silencio').

    Returns:
        Trechos relevantes do regulamento para responder à dúvida.
    """
    if not REGULAMENTO_PATH.exists():
        return "Regulamento não encontrado."

    content = REGULAMENTO_PATH.read_text(encoding="utf-8")
    chapters = content.split("## ")

    keywords = [k.lower().strip() for k in re.split(r"\s+", duvida) if len(k) > 2]
    matched_sections = []

    for chapter in chapters:
        if not chapter.strip():
            continue
        chapter_title = chapter.split("\n")[0]
        chapter_lower = chapter.lower()

        # Check if any keyword matches this chapter
        matches = sum(1 for kw in keywords if kw in chapter_lower)
        if matches > 0:
            # Extract relevant articles/paragraphs rather than entire massive chapter if too long
            matched_sections.append(f"## {chapter.strip()}")

    if not matched_sections:
        # Fallback to general terms or return summary of chapters
        return "Não foram encontrados trechos específicos do regulamento para esta dúvida. Por favor, especifique o assunto (ex: piscina, academia, barulho, garagem, animais)."

    # Return matched sections (capped if multiple to avoid context blowup)
    return "\n\n".join(matched_sections[:2])
