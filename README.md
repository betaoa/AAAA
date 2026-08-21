# videobot no GitHub Actions

Gera e posta 3 vídeos por dia, sozinho, em repositório **privado** e sem pagar nada.

## O que mudou em relação à versão anterior

Quatro defeitos impediam a primeira execução:

1. `postar.yml` estava na raiz. O Actions só lê workflows em `.github/workflows/`. Aqui já está no lugar certo.
2. O passo do token do YouTube usava `if: ${{ secrets.YOUTUBE_TOKEN != '' }}`. O contexto `secrets` não é aceito em `if:` de passo — o workflow inteiro era rejeitado antes de rodar. Agora o teste é feito dentro do shell.
3. `cache: pip` sem nenhum `requirements.txt` no repositório faz o passo falhar. Agora existe `requirements.txt`, e o cache funciona de verdade.
4. Faltava o pacote `toml`. Ele é importado por `app/config/config.py` do MoneyPrinterTurbo e não aparece no `requirements.txt` de lá (naquele projeto ele entra de carona com o streamlit, que aqui não é instalado). Sem ele, nada roda. Testado: sem `toml`, o import quebra; com ele, a esteira vai até o fim.

Além disso: o artefato de vídeo agora só é guardado no modo teste (3 vídeos/dia × 7 dias estouram os 500 MB gratuitos de armazenamento), o job tem teto de 30 min, o `git push` refaz rebase se colidir, e o modelo do Gemini virou configurável.

## Ressalvas honestas

**Minutos — número medido, não estimativa.** A primeira execução completa levou **13m55s**: ~1 min de preparo (37s de ffmpeg, 16s de dependências, 5s de clone) e ~13 min de render. O GitHub cobra por minuto iniciado, então conte 14.

| Vídeos por dia | Minutos/mês | Cabe nos 2.000? |
|---|---|---|
| 2 | 840 | sim, folgado |
| 3 | 1.260 | sim, 37% de folga |
| 4 | 1.680 | sim, no limite |
| 5 | 2.100 | **não** |

Ou seja: no plano gratuito com repositório **privado**, 4 por dia é o teto.

**Este repositório é público**, e em repositório público os minutos do Actions são ilimitados. A tabela acima só volta a valer se ele for fechado de novo. O que muda por ser público: o código e os logs das execuções ficam visíveis para qualquer um. Os secrets continuam escondidos — o GitHub os mascara automaticamente no log, e este workflow só dispara por agendamento ou na mão, nunca por pull request de fork, que é o caminho pelo qual um repositório público costuma vazar segredo.

**Cota do YouTube.** 10.000 unidades por dia, cada upload custa 1.600. Teto real: 6 vídeos por dia. Três cabem. Dez não cabem.

**Termos de uso.** O GitHub diz que o Actions não deve ser usado para atividade não relacionada ao projeto do repositório. É zona cinza, não garantia. Se bloquearem, o mesmo pacote roda na Oracle ou no seu PC sem alteração.

**Atraso.** O cron do GitHub pode disparar até ~15 min depois do horário. Irrelevante para janela de audiência.

**Hibernação.** Agendamento é desligado após 60 dias sem atividade no repositório. O workflow faz um commit a cada execução, então ele se mantém vivo sozinho.

## Passo a passo

**1. Subir os arquivos**

No repositório: *Add file → Upload files*, e arraste **a pasta inteira** deste pacote (não os arquivos soltos — a pasta `.github` precisa vir junto). Estrutura final:

```
.github/workflows/postar.yml
requirements.txt
rodar.py
youtube_post.py
tiktok_post.py
temas.txt
usados.txt
historico.jsonl
.gitignore
```

Se já existir um `postar.yml` solto na raiz, apague — não serve para nada ali.

**2. Segredos**

`Settings → Secrets and variables → Actions → New repository secret`

| Nome | Onde pegar |
|---|---|
| `PEXELS_KEY` | pexels.com/api — grátis |
| `GEMINI_KEY` | aistudio.google.com/apikey — grátis |
| `YOUTUBE_TOKEN` | conteúdo inteiro do `youtube_token.json` |

Sem o `YOUTUBE_TOKEN` o bot roda e gera o vídeo, só não posta. Serve para testar.

**3. Modelo do Gemini (opcional, mas leia)**

O padrão do MoneyPrinterTurbo é um modelo `pro-preview`, que costuma ficar fora da cota gratuita. O workflow usa `gemini-flash-latest` no lugar. Se der erro 404 ou de cota, troque em `Settings → Secrets and variables → Actions → Variables → New variable`, nome `GEMINI_MODEL`, com o nome de outro modelo. Deixar a variável vazia devolve o padrão do MPT.

**4. O token do YouTube**

No seu PC, uma vez só:

```bash
pip install google-auth-oauthlib google-api-python-client
python3 youtube_post.py auth
```

**Antes disso**, no Google Cloud Console: depois de criar a tela de consentimento OAuth, clique em **"Publish app" / "Publicar aplicativo"**. Se ela ficar em modo *Testing*, o refresh token do Google **expira em 7 dias** e o bot para de postar sem aviso claro. Publicado, ele não expira. O app continua não verificado e mostra uma tela de aviso na hora de autorizar — é só clicar em "Avançado" e continuar. Para uso no seu próprio canal, isso basta.

**5. Ligar**

Aba `Actions` → habilita → `videobot` → `Run workflow` → marca **teste** → `Run`.

Em alguns minutos o vídeo aparece em *Artifacts*, na página da execução. Confere antes de deixar postar de verdade.

**6. Soltar**

Roda de novo sem marcar *teste*. A partir daí dispara sozinho **quatro vezes por dia**: 9h, 12h, 14h e 20h30 (horário de Cuiabá). O vídeo entra no ar uns 15 minutos depois de cada disparo, que é o tempo de gerar.

## Como acompanhar

- `Actions` → cada execução tem log completo
- `historico.jsonl` → uma linha por vídeo postado, com o link
- `usados.txt` → temas já queimados; quando acabam os 45, a lista zera e recomeça

## A pauta se renova sozinha

Antes de cada geração o bot roda o `temas_auto.py`, que refaz a lista de temas em vez de sortear de uma lista fixa. O caminho é este:

1. Puxa os vídeos **mais populares do YouTube** no Brasil e nos Estados Unidos pela Data API. Isso é tendência de verdade, medida, não palpite. Custa 1 unidade das suas 10.000 diárias por região.
2. Manda esses títulos ao Gemini, com a busca do Google ligada quando a cota permitir, e pede temas novos no formato `nicho|tema|termos`.
3. Descarta o que está malformado, o que repete tema já usado, e o que traz termos de busca em português — o acervo do Pexels em português é pobre.
4. Reescreve o `temas.txt`, novos primeiro, cortando a cauda em 200 linhas.

Se qualquer etapa falhar, **a lista anterior fica intacta**. O bot nunca fica sem tema por causa disso.

Para ligar a parte de tendência real, cadastre mais um secret:

| Nome | Onde pegar |
|---|---|
| `YOUTUBE_API_KEY` | Google Cloud Console → Credenciais → Chave de API, restrita à YouTube Data API v3 |

Sem esse secret o bot continua funcionando: ele apenas gera temas sem o termômetro do que está em alta, o que é bem pior, porque o modelo passa a inventar tendência a partir do que aprendeu no treino.

### O que isso não faz

Vale ser exato, para você não esperar o que não existe:

- **Não analisa TikTok nem Instagram.** Nenhuma das duas tem API pública que entregue o que está em alta. A do TikTok exige aprovação comercial e não serve para isso; a do Instagram só enxerga a sua própria conta.
- **Não copia estilo de edição.** Corte, ritmo e gancho visual não são observáveis por API em plataforma nenhuma. O que se extrai é metadado: título, descrição, tags, views. Dá para inferir padrão de assunto e de título. Não dá para inferir montagem.
- **Não aprende com o próprio resultado.** Variar tema não é melhorar. Para o bot melhorar de fato ele precisaria saber quais dos *seus* vídeos deram certo, o que exige a YouTube Analytics API e um escopo OAuth a mais — ou seja, refazer a autorização. É o próximo passo natural, e ainda não está feito.

## Como mudar as coisas

**Temas:** o arquivo `temas.txt` é reescrito a cada execução pelo `temas_auto.py`, então editar na mão só vale para o próximo vídeo — depois disso suas linhas vão sendo empurradas para o fim da lista. Para mudar o rumo de verdade, mexa nos nichos sugeridos e nas regras dentro do `temas_auto.py`, que é o que orienta o Gemini.

**Horários:** edita os `cron` no `postar.yml`. É UTC, e Cuiabá é UTC−4. Os minutos são quebrados de propósito (`5`, `7`, `35`): todo mundo agenda no minuto zero, e é ali que a fila do GitHub mais atrasa.

**Quantidade:** cada linha de `cron` é um vídeo por dia. O GitHub deixou de ser o limite quando o repositório virou público. O teto agora é a cota do YouTube: 10.000 unidades por dia, 1.600 por upload, ou seja **6 vídeos/dia no máximo** — e nesse número sobram 390 unidades, menos de um quarto de um upload, então uma única tentativa de reenvio já estoura. Com 5 sobram 2.000, que é margem de verdade.

**Estilo de narração:** o `rodar.py` manda um `--video-script-prompt` junto com o tema, que orienta o tom — locutor falando direto, gancho na primeira frase, sem "você sabia" e sem pedir inscrição. Tem variação por nicho no dicionário `ESTILOS`. Os nichos `dorama` e `anime` levam uma instrução a mais: não inventar nome de obra, ator ou número, porque é exatamente aí que o modelo alucina com mais confiança.

Não suba para 10 por dia logo de cara. Conta nova com volume alto de vídeo gerado por IA é o padrão que os algoritmos marcam como spam. E 10 por dia não cabe na cota do YouTube. Sobe para 4 ou 5 depois de duas ou três semanas sem queda de alcance.
