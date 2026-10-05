import re
import unicodedata
from pathlib import Path

REGULAMENTO_PATH = Path(__file__).parent.parent.parent / "dados" / "regulamento.md"
ARTICLE_PATTERN = re.compile(r"(?m)^\*\*Art\.\s*\d+[ºo.]?\*\*")
CHAPTER_PATTERN = re.compile(r"(?m)^##\s+")
STOP_WORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "me",
    "minha",
    "meu",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "qual",
    "quais",
    "que",
    "se",
    "sem",
    "sobre",
    "sua",
    "suas",
    "seu",
    "seus",
    "um",
    "uma",
    "umas",
    "uns",
    "voce",
    "voces",
    "regulamento",
    "interno",
}
QUERY_EXPANSIONS = {
    "horario": {"periodo", "funciona", "disponivel", "horas"},
    "barulho": {"ruido", "ruidos", "sossego"},
    "ruido": {"barulho", "sossego"},
    "visitante": {"convidado", "convidados"},
    "animal": {"animais", "pet", "pets"},
}


def _normalizar_termos(texto: str) -> set[str]:
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    sem_acentos = "".join(
        caractere for caractere in normalizado if not unicodedata.combining(caractere)
    )
    return {
        termo
        for termo in re.findall(r"[a-z0-9]+", sem_acentos)
        if len(termo) > 2 and termo not in STOP_WORDS
    }


def _extrair_artigos(conteudo: str) -> list[str]:
    marcadores = list(ARTICLE_PATTERN.finditer(conteudo))
    artigos = []
    for indice, marcador in enumerate(marcadores):
        proximo_artigo = (
            marcadores[indice + 1].start()
            if indice + 1 < len(marcadores)
            else len(conteudo)
        )
        trecho = conteudo[marcador.start() : proximo_artigo]
        proximo_capitulo = CHAPTER_PATTERN.search(trecho)
        if proximo_capitulo:
            trecho = trecho[: proximo_capitulo.start()]
        artigos.append(trecho.strip())
    return artigos


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
    termos_duvida = _normalizar_termos(duvida)
    for termo in termos_duvida.copy():
        termos_duvida.update(QUERY_EXPANSIONS.get(termo, set()))

    artigos = _extrair_artigos(content)
    artigos_relevantes = []
    for artigo in artigos:
        termos_artigo = _normalizar_termos(artigo)
        correspondencias = termos_duvida & termos_artigo
        if correspondencias:
            artigos_relevantes.append(
                (
                    len(correspondencias),
                    sum(artigo.lower().count(t) for t in correspondencias),
                    artigo,
                )
            )

    if not artigos_relevantes:
        return "Não foram encontrados trechos específicos do regulamento para esta dúvida. Por favor, especifique o assunto (ex: piscina, academia, barulho, garagem, animais)."

    return max(artigos_relevantes, key=lambda resultado: (resultado[0], resultado[1]))[
        2
    ]
