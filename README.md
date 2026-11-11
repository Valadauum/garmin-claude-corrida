# garmin-claude-corrida

Seus dados do Garmin dentro do **Claude Code**, para analisar treinos e provas de corrida e trail e planejar a próxima prova junto com o seu treinador.

O repositório tem duas partes:

- **[GUIA-CLAUDE.md](GUIA-CLAUDE.md)**: o passo a passo. A Parte 1 é a instalação, que você faz em 5 minutos. A Parte 2 são as instruções para colar no Claude. Com elas o Claude faz o relatório da temporada, o estudo de evolução e recordes, o D+ de esteira e escada, o plano de prova com cartão de ritmo e nutrição hora a hora, e o planejamento da prova-alvo do ano.
- **[scripts/](scripts)**: ferramentas em Python para usar fora do Claude ou para o Claude rodar.

> Os dados vêm do servidor MCP [`garmin-personal-mcp`](https://pypi.org/project/garmin-personal-mcp/), que usa a API pessoal do Garmin Connect. Ele não faz parte deste repositório.

## Instalação rápida

1. Instale o [uv](https://docs.astral.sh/uv/):
   - Windows (PowerShell):
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - Mac/Linux:
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
2. Salve a sua chave da API pessoal do Garmin e confira se ela funciona:
   ```bash
   uvx garmin-personal-mcp auth
   uvx garmin-personal-mcp auth --check
   ```
3. Conecte o servidor ao Claude Code:
   ```bash
   claude mcp add --scope user garmin-personal -- uvx garmin-personal-mcp
   ```
4. Abra uma conversa nova no Claude, cole o [GUIA-CLAUDE.md](GUIA-CLAUDE.md) e diga: *"Siga a Parte 2 em diante comigo"*.

## Scripts

Todos usam a chave salva no passo 2.

| Script | O que faz |
|---|---|
| `scripts/garmin_mcp.py` | Cliente mínimo do servidor MCP, para chamar qualquer ferramenta `garmin_*` por linha de comando ou como módulo. Já pagina a busca de atividades. |
| `scripts/prova_por_hora.py` | Lê o `.fit` de uma prova e mostra, hora a hora, km, D+, D−, FC média e máxima e % do tempo parado, mais o tempo acima de limiares de FC. Mostra se você largou forte demais. |
| `scripts/dplus_indoor.py` | Estima o D+ de esteira inclinada e escada, que o Garmin grava como zero. Usa a inclinação escrita pelo treinador no treino estruturado e, quando ela não existe, a FC. Gera um CSV por sessão. |

Exemplos:

```bash
cd scripts
python garmin_mcp.py tools
python garmin_mcp.py call garmin_get_day '{"date": "2026-11-05"}'
uv run --with fitdecode prova_por_hora.py minha-prova.fit
uv run --with fitdecode dplus_indoor.py --inicio 2026-01-01 --fim 2026-12-31 -o dplus.csv
```

### Quirks da API que valem saber

- `garmin_search_activities`: use `limit: 100` e pagine com `offset` (limites altos devolvem HTTP 500).
- `garmin_get_hrv_summaries`: peça períodos de até 28 dias.
- `garmin_download_activity`: salva só dentro de `Downloads/garmin/<subpasta>` (ou da pasta definida em `GARMIN_MCP_DOWNLOAD_DIR`).
- A variável `GARMIN_PERSONAL_API_KEY` substitui a chave salva, o que permite um segundo servidor com a chave de outra pessoa. Só faça isso com o consentimento dela, e quem digita a chave é o dono dela.

## Privacidade

O `.gitignore` bloqueia `.fit`, `.zip`, `.csv` e `.json`, para que nenhum dado de saúde vá parar no repositório por acidente. Os relatórios que o Claude gera ficam como páginas privadas na sua conta. Você compartilha o que quiser pelo menu Share.

## Aviso

É uma ferramenta de leitura de dados. Ela não substitui treinador, nutricionista nem avaliação médica. As estimativas, como o D+ de esteira e escada e as previsões de tempo, vêm marcadas com o nível de confiança.

Licença MIT.
