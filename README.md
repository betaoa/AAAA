# videobot no GitHub Actions

Gera e posta 3 vídeos por dia, sozinho, sem cartão de crédito e sem máquina ligada em casa.

## Por que isso é melhor que a Oracle

| | Oracle Always Free | GitHub Actions |
|---|---|---|
| Cartão de crédito | exige | **não exige** |
| "Out of host capacity" | problema crônico | não existe |
| CPU | 2 núcleos ARM | **4 núcleos** |
| RAM | 12 GB | 16 GB |
| Render por vídeo | ~9 min | **~4 min** |
| Agendamento | cron da máquina | embutido |
| Conta derrubada sem aviso | há relatos | raro |

## Ressalvas honestas

**Minutos.** Repositório privado tem 2.000 minutos grátis por mês. Três execuções por dia a ~12 min dão ~1.100 min/mês. Cabe, mas sem folga grande. Repositório público tem minutos ilimitados — o código fica visível, mas os secrets continuam escondidos. Se estourar, o job simplesmente para até o mês virar.

**Termos de uso.** O GitHub diz que o Actions não deve ser usado para atividade não relacionada ao projeto do repositório. Aqui o código do bot mora no próprio repositório e o que ele publica é a saída dele, o que é defensável — mas é zona cinza, não garantia. Se um dia bloquearem, o mesmo pacote roda na Oracle ou no seu PC sem alteração.

**Atraso.** O cron do GitHub pode disparar até ~15 min depois do horário quando a fila está cheia. Para janela de audiência isso é irrelevante.

**Repositório público hiberna.** Agendamento em repo público é desligado após 60 dias sem commit. O workflow faz um commit a cada execução, então ele se mantém vivo sozinho.

## Passo a passo

**1. Conta e repositório**

Cria conta em github.com (grátis, sem cartão). Cria um repositório novo — recomendo **privado** no começo.

**2. Sobe estes arquivos**

```
.github/workflows/postar.yml
rodar.py
youtube_post.py
temas.txt
```

Dá pra arrastar pela interface do site, em *Add file → Upload files*. Não precisa saber git.

**3. Cadastra os segredos**

`Settings → Secrets and variables → Actions → New repository secret`

| Nome | Onde pegar |
|---|---|
| `PEXELS_KEY` | pexels.com/api — grátis |
| `GEMINI_KEY` | aistudio.google.com/apikey — grátis, 1.500 chamadas/dia |
| `YOUTUBE_TOKEN` | conteúdo inteiro do `youtube_token.json` |

O `youtube_token.json` sai de rodar, **no seu PC**, uma vez só:

```bash
pip install google-auth-oauthlib google-api-python-client
python3 youtube_post.py auth
```

Sem o `YOUTUBE_TOKEN` o bot ainda roda e gera o vídeo — só não posta. Serve pra testar.

**4. Liga**

Aba `Actions` → habilita → `videobot` → `Run workflow` → marca **teste** → `Run`.

Em ~5 minutos aparece o vídeo em *Artifacts*, na página da execução. Confere se ficou bom antes de deixar postar de verdade.

**5. Solta**

Roda de novo sem marcar *teste*. A partir daí ele dispara sozinho às 12h, 19h e 21h.

## Como acompanhar

- `Actions` → cada execução tem log completo
- `historico.jsonl` → uma linha por vídeo postado, com o link
- `usados.txt` → temas já queimados; quando acabam os 45, a lista zera e recomeça

## Como mudar as coisas

**Temas:** edita `temas.txt`. Formato `nicho|tema|termos de busca em inglês`. Os termos precisam ser em inglês — o acervo do Pexels em português é pobre.

**Horários:** edita os `cron` no `postar.yml`. Lembra que é UTC, e Cuiabá é UTC-4.

**Quantidade:** cada linha de `cron` é um vídeo por dia. Quer 2 em vez de 3, apaga uma linha.

Não suba pra 10 por dia logo de cara. Conta nova com volume alto de vídeo gerado por IA é o padrão que os algoritmos marcam como spam. Sobe pra 4 ou 5 depois de duas ou três semanas sem queda de alcance.
