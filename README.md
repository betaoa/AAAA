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

**Minutos.** Repositório privado tem 2.000 minutos grátis por mês. Cada execução gasta ~2 min de preparo (ffmpeg, clone, dependências com cache) mais o render. Se o render for de 8 min, são ~10 min por execução, ~900/mês. Se for de 15, são ~1.550/mês. Cabe nos dois casos, mas sem folga larga. Confira o gasto real em *Settings → Billing* depois da primeira semana. Se apertar: apague uma linha de `cron`.

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

Roda de novo sem marcar *teste*. A partir daí dispara sozinho às 12h, 19h e 21h.

## Como acompanhar

- `Actions` → cada execução tem log completo
- `historico.jsonl` → uma linha por vídeo postado, com o link
- `usados.txt` → temas já queimados; quando acabam os 45, a lista zera e recomeça

## Como mudar as coisas

**Temas:** edita `temas.txt`. Formato `nicho|tema|termos de busca em inglês`. Os termos precisam ser em inglês — o acervo do Pexels em português é pobre.

**Horários:** edita os `cron` no `postar.yml`. É UTC, e Cuiabá é UTC-4.

**Quantidade:** cada linha de `cron` é um vídeo por dia.

Não suba para 10 por dia logo de cara. Conta nova com volume alto de vídeo gerado por IA é o padrão que os algoritmos marcam como spam. E 10 por dia não cabe na cota do YouTube. Sobe para 4 ou 5 depois de duas ou três semanas sem queda de alcance.
