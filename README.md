# Videobot v7 — Drive, 31 nichos e 3 redes

Uma central controla todos os perfis. Cada nicho tem pasta própria no Google
Drive, estado separado e agenda de **5 vídeos por dia** para YouTube,
Instagram e TikTok.

O projeto não cria contas sociais nem contorna login, verificação ou análise
das plataformas. Os 31 perfis estão cadastrados com `ativo: false` para não
publicar na conta errada. Cada perfil deve ser ativado depois que os tokens da
conta correspondente forem cadastrados.

## O que já está preparado

- 31 nichos únicos em `config/canais.yml`;
- 5 horários diários no fuso de Cuiabá;
- seleção de um MP4 ainda não usado na pasta correta do Drive;
- publicação independente nas três plataformas;
- histórico e lista de vídeos usados por perfil;
- repetição segura quando uma rede falha;
- execução no GitHub Actions, Windows ou Termux;
- modo antigo de gerar vídeos continua disponível com `modo: gerar`.

As pastas duplicadas de Family Guy e do pacote sem identificação foram
ignoradas no cadastro.

## 1. Drive: duas formas de leitura

### Preferida no Windows: Google Drive para computador

Espelhe `Vídeos por Nicho` no computador e informe a pasta em `.env`:

```text
DRIVE_SYNC_ROOT=G:\Meu Drive\Vídeos por Nicho
```

O bot entra automaticamente na subpasta com o mesmo nome do perfil e envia o
MP4 dali. Nesse modo a central continua privada, nenhum token do Drive fica no
GitHub e o vídeo não é baixado duas vezes.

### Servidor, GitHub ou Termux

Cada perfil aponta para sua pasta:

```yaml
- id: limpeza
  nome: Limpeza
  ativo: false
  nichos: [limpeza]
  drive_url: https://drive.google.com/drive/folders/ID_DA_PASTA
```

Se a pasta for pública, o link basta. Como a central atual é privada, o
GitHub precisa de um Secret chamado `DRIVE_CREDENTIALS`, contendo o JSON de
uma conta de serviço ou token OAuth com leitura do Drive. Compartilhar somente
a pasta central com a conta de serviço dá acesso às subpastas por herança.

Quando não existe pasta sincronizada, o bot baixa somente o vídeo escolhido
para aquele horário. Depois de ao menos
uma rede aceitar a postagem, salva o ID em:

```text
dados/<perfil>/drive_usados.txt
```

## 2. Contas e tokens por perfil

No GitHub, use o ID do perfil em maiúsculas, trocando hífen por sublinhado.
Para o perfil `limpeza`:

```text
YOUTUBE_TOKEN_LIMPEZA
IG_USER_ID_LIMPEZA
IG_TOKEN_LIMPEZA
TIKTOK_TOKEN_LIMPEZA
```

Para `carros-caminhoes`:

```text
YOUTUBE_TOKEN_CARROS_CAMINHOES
IG_USER_ID_CARROS_CAMINHOES
IG_TOKEN_CARROS_CAMINHOES
TIKTOK_TOKEN_CARROS_CAMINHOES
```

No PC ou Termux, arquivos de token ficam em:

```text
secrets/youtube-<perfil>.json
secrets/tiktok-<perfil>.json
secrets/drive_credentials.json
```

## 3. Ativar sem risco

Primeiro teste um perfil sem publicar:

```bash
python videobot.py validar
python videobot.py rodar --canal limpeza --teste
```

Para gerar um Short sobre um assunto escolhido, use `--tema`. O tema vale
apenas para esta execucao: mesmo em um canal configurado para Drive, o video
sera gerado, sem mudar a configuracao, os arquivos do Drive ou a agenda.
`--termos` permite indicar buscas visuais ao renderizador. O tema manual nao
consome a lista automatica de `temas.txt`.

```bash
python videobot.py rodar --canal inteligencia-artificial --tema "Como funciona um buraco negro" --teste
python videobot.py rodar --canal inteligencia-artificial --tema "Como funciona um buraco negro" --termos "black hole space galaxy stars" --teste
```

Confira o MP4 baixado em `dados/limpeza/downloads/`. Depois cadastre os tokens
das três contas de Limpeza e mude somente esse perfil para:

```yaml
ativo: true
```

Repita por nicho. O comando abaixo mostra o modo, redes, horários e estado de
todos os perfis:

```bash
python videobot.py listar
```

## 4. GitHub Actions

O workflow verifica a agenda duas vezes por hora. No modo Drive ele não baixa
o renderizador nem exige Gemini/Pexels. Para teste manual:

1. Actions → `videobot-v7` → Run workflow;
2. informe o ID, por exemplo `limpeza`;
3. mantenha `teste` marcado.

Secrets compartilhados:

```text
DRIVE_CREDENTIALS
TIKTOK_CLIENT_KEY
TIKTOK_CLIENT_SECRET
```

Variables recomendadas:

```text
TIKTOK_DIRECT_POST=1
TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE
TIKTOK_REDIRECT_URI=https://seu-endereco-de-retorno
IG_GRAPH_VERSION=vXX.X
```

## 5. O limite real de cada plataforma

### YouTube

O upload usa OAuth da conta/canal correspondente. A API do YouTube documenta
um limite padrão próprio de 100 uploads por dia por projeto; projetos de API
não auditados podem ter uploads forçados para privado.

Documentação: https://developers.google.com/youtube/v3/docs/videos/insert

### Instagram

Publica Reels pela API oficial. Cada perfil precisa ser profissional, estar
vinculado corretamente na Meta e conceder as permissões de publicação.

### TikTok

Com `TIKTOK_DIRECT_POST=1`, usa o endpoint oficial de publicação direta. Isso
exige app aprovado para `video.publish` e autorização de cada conta. Cliente
TikTok não auditado fica restrito a publicação privada. Sem essa variável o
vídeo vai para rascunho e ainda precisa ser confirmado no aplicativo.

Documentação: https://developers.tiktok.com/docs/en/content-posting-api-get-started

## 6. Agenda e estado

Horários padrão: `09:05`, `11:47`, `14:05`, `17:11`, `20:35`.

```text
dados/<perfil>/agenda.json
dados/<perfil>/drive_usados.txt
dados/<perfil>/historico.jsonl
```

Uma falha total não marca o vídeo como usado. Se ao menos uma rede aceitar a
postagem, o histórico registra o resultado das três e o próximo horário usa
outro arquivo.

Publique somente material que você tem autorização para reutilizar; o bot não
altera direitos autorais do conteúdo das pastas.
