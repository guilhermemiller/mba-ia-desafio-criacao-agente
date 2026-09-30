# Regra é regra: Assistente Virtual do Residencial Aurora

API de atendimento e assistente virtual para os moradores do Residencial Aurora construída com **Google ADK**, **FastAPI** e o **SDK oficial da OpenAI para Python** em Python 3.12. O modelo pode ser servido por qualquer endpoint compatível com a API OpenAI, incluindo o servidor local configurado no projeto.

## Arquitetura

O sistema é dividido entre um **Agente Principal (Coordenador)** e três **Especialistas**, garantindo especialização e separação clara de responsabilidades:

1. **Agente Principal (`assistente_principal`)**:
   - **Responsabilidade**: Atendimento inicial e roteamento/delegação para os especialistas adequados.
   - **Acionamento**: Acionado diretamente pelo Runner do ADK em cada mensagem do morador.
   - **Instruções**: Focadas estritamente em cortesia, roteamento e reforço das diretrizes de segurança (apartamento preso à sessão e bloqueio de confirmação direta por texto). Não possui o regulamento em suas instruções.

2. **Especialista em Reservas (`especialista_reservas`)**:
   - **Responsabilidade**: Consultar reservas, checar disponibilidade de áreas comuns (salão de festas, churrasqueira, quadra), solicitar reservas e cancelar reservas do próprio apartamento.
   - **Tools**: `consultar_minhas_reservas`, `checar_disponibilidade_area`, `solicitar_reserva_area`, `cancelar_reserva_area`.
   - **Motivo**: Isola a lógica e as tools de reservas, evitando contaminação com outras áreas.

3. **Especialista em Visitantes (`especialista_visitantes`)**:
   - **Responsabilidade**: Consultar autorizações e solicitar liberação de entrada para visitantes.
   - **Tools**: `consultar_meus_visitantes`, `solicitar_autorizacao_visitante`.
   - **Motivo**: Foca no fluxo de portaria e liberação de acesso.

4. **Especialista em Regulamento (`especialista_regulamento`)**:
   - **Responsabilidade**: Responder dúvidas dos moradores sobre o regulamento interno.
   - **Tools**: `buscar_regulamento`.
   - **Motivo**: Garante a consulta dinâmica ao regulamento sem carregar o texto completo na memória ou na sessão.

---

## Garantias

### Garantia 1: Cobrança ou acesso só com confirmação
- **Arquivo / Trecho**: `src/tools/reservas_tools.py` (`solicitar_reserva_area`), `src/tools/visitantes_tools.py` (`solicitar_autorizacao_visitante`) e `src/main.py` (`responder_confirmacao`).
- **Como funciona**: Reservas de áreas com taxa (`taxa > 0`) e autorizações de visitantes criam um registro em estado `pending` na tabela `confirmacoes` no banco de dados e retornam o `id` em `confirmacoes_pendentes` na resposta da API. O código do agente não grava a reserva/visitante até que a rota `POST /sessoes/{session_id}/confirmacoes` receba `confirmado: true`. Se o morador tentar confirmar via texto no chat, as instruções do agente e o fluxo em código bloqueiam e instruem a usar o sistema formal. Reenvios ou IDs inválidos retornam `HTTP 409`.

### Garantia 2: Cada sessão pertence a um apartamento
- **Arquivo / Trecho**: `src/main.py` (`criar_sessao`), `src/storage/repository.py` e `src/tools/reservas_tools.py` / `src/tools/visitantes_tools.py`.
- **Como funciona**: O apartamento é vinculado exclusivamente na criação da sessão (`POST /sessoes`) e armazenado no estado da sessão (`adk_session.state["apartamento"]`). Todas as ferramentas leem o apartamento diretamente de `tool_context.state["apartamento"]`, ignorando qualquer número de apartamento informado no texto do usuário ou fornecido pelo modelo. Consultas e cancelamentos são filtrados estritamente pelo apartamento da sessão.

### Garantia 3: Nada se perde no reinício
- **Arquivo / Trecho**: `src/db.py` e `src/storage/repository.py`.
- **Como funciona**: O banco de dados SQLite (`aurora.db`) armazena de forma persistente todas as sessões, histórico de eventos (`eventos`), confirmações, reservas e visitantes. A reinicialização da API não afeta a persistência e permite a continuidade perfeita das conversas existentes.

### Garantia 4: O regulamento é consultado, não carregado
- **Arquivo / Trecho**: `src/tools/regulamento_tools.py` (`buscar_regulamento`) e `src/agents/main_agent.py`.
- **Como funciona**: As instruções do agente principal não contêm o texto do regulamento. Quando uma dúvida é enviada, o `especialista_regulamento` executa a tool `buscar_regulamento`, que pesquisa palavras-chave em `dados/regulamento.md` e retorna apenas os capítulos/seções relevantes para a dúvida específica, evitando o estouro do contexto e a poluição do histórico com capítulos não relacionados.

### Garantia 5: Dois moradores, uma reserva
- **Arquivo / Trecho**: `src/db.py` (Constraint `UNIQUE(area, data)`) e `src/storage/repository.py` (`criar_reserva`).
- **Como funciona**: A exclusividade é garantida no nível do banco de dados no momento exato da gravação (`INSERT INTO reservas`), através de uma transação `BEGIN IMMEDIATE` e da restrição `UNIQUE(area, data)`. Caso duas requisições simultâneas tentem reservar a mesma área para a mesma data, o SQLite bloqueia a segunda gravação lançando `IntegrityError`, que é capturado pelo código e convertido em uma resposta graciosa sem erro de servidor (`500`).

---

## Como rodar

### Pré-requisitos
- Python 3.12 ou superior
- Gerenciador de pacotes `uv`

### Configuração do Ambiente (`.env`)
1. Copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure as variáveis do SDK OpenAI:
   ```env
   OPENAI_API_KEY=sua_chave_ou_token_do_servidor_local
   OPENAI_BASE_URL=http://localhost:20128/v1
   MODEL_NAME=freecoding
   PORT=8000
   DATABASE_PATH=aurora.db
   ```

`OPENAI_API_KEY` é obrigatória para executar os testes com LLM. Para um servidor local OpenAI-compatible, use o endereço configurado pelo servidor e o identificador de modelo anunciado por ele. Não compartilhe nem versione o arquivo `.env`; use `.env.example` como modelo sem credenciais reais.

### Instalação das Dependências
Instale os pacotes com o `uv`:
```bash
uv sync
```

### Restaurar Dados Iniciais
Para inicializar o banco de dados SQLite e restaurar os dados dos arquivos em `dados/`:
```bash
uv run python scripts/restore_data.py
```

### Subir a API
Execute o servidor da API com Uvicorn:
```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
A API responderá na URL: `http://localhost:8000`.

### Testes
O comando padrão executa todos os testes, inclusive o fluxo avaliador que faz chamadas reais à LLM. Portanto, o servidor configurado em `OPENAI_BASE_URL` precisa estar acessível e `OPENAI_API_KEY` precisa estar definida. O teste LLM não é ignorado por padrão e não depende de `RUN_LLM_TESTS`.

Execute a suíte listando cada teste:
```bash
uv run pytest -v
```

Para exibir também os marcadores de início e conclusão de cada passo do fluxo LLM, use `-s`:
```bash
uv run pytest tests/test_evaluator_flow.py -v -s
```

Opções úteis:

| Opção | Efeito |
| --- | --- |
| `-v` | Lista cada teste individualmente e seu resultado. |
| `-s` | Exibe os `print`s do teste em tempo real, incluindo modelo e passos `[PASSO NN]`. |
| `-q` | Saída resumida; não use junto com `-v` quando quiser ver cada teste. |
| `-k texto` | Executa testes cujo nome corresponda ao texto. |

Exemplos para executar apenas um grupo ou localizar um teste:
```bash
uv run pytest tests/test_api.py -v
uv run pytest -k concurrency -v
```

O fluxo avaliador imprime `[PASSO NN] Iniciando` antes das ações e `[PASSO NN] OK` depois das verificações. Se uma asserção falhar, o último marcador indica o passo que estava em execução. Para conferir a configuração Ruff:
```bash
uv run ruff check .
```
