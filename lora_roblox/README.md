# LoRA Luau/Roblox (3D + VFX por script)

Treina um adaptador LoRA em um LLM de código para gerar **Luau** que monta
modelos 3D (Parts/Models) e efeitos (ParticleEmitter, Trail, Beam, Tween).

## Escopo (o que este LoRA NÃO faz)
- **Som**: exige modelo de áudio (MusicGen, Stable Audio). Pipeline separado.
- **Malhas 3D reais (.obj/.fbx)**: exige modelo generativo de 3D. Aqui o "3D" é
  código que constrói geometria com Parts.

## Estrutura
```
dataset/seed.jsonl            exemplos-semente (formato de referência)
scripts/make_seed_dataset.py  gera seed.jsonl
scripts/validate_dataset.py   valida JSONL (+ luau-analyze se instalado)
scripts/train_lora.py         treino SFT com LoRA
scripts/generate.py           testa adaptador vs. modelo base
```

## Formato do dataset (JSONL, uma linha por exemplo)
```json
{"tags": ["vfx"], "messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "pedido em linguagem natural"},
  {"role": "assistant", "content": "```lua\n...codigo...\n```"}]}
```
A perda é calculada **só na resposta do assistant**.

## Quantos exemplos?
Os 6 do `seed.jsonl` só fixam o formato. Estimativa (sem medição própria,
baseada na prática comum de SFT por LoRA): ~300–1.000 exemplos de boa qualidade
para mudar estilo/formato de forma perceptível; mais que isso para cobrir APIs
variadas. Qualidade e diversidade pesam mais que volume.

## Onde obter exemplos (verifique a licença de cada fonte)
| Fonte | Uso | Observação |
|---|---|---|
| Roblox Creator Docs (repositório `Roblox/creator-docs`) | Trechos de código e explicações de API | Verificar a licença atual no repositório antes de usar |
| Luau (`luau-lang/luau`) | Sintaxe, tipagem | Verificar a licença |
| Seus próprios scripts/jogo | Melhor alinhamento ao seu projeto | Sem risco de licença |
| Exemplos gerados por LLM e **revisados** | Escalar volume | Rodar no Studio ou `luau-analyze`; descartar o que falhar |

Não faça scraping do Creator Store: licenças e termos variam por asset.
Cada exemplo gerado por LLM precisa passar por `validate_dataset.py` e por um
teste real no Studio (a sintaxe válida não garante que o efeito fique correto).

## Hardware: RX 9060 XT (AMD, RDNA4)
Fatos que dependem da sua versão e que **não pude verificar neste container**
(sem GPU):
- Há variantes de 8 GB e 16 GB. Com 16 GB, modelo de 3B em bf16 com LoRA e
  gradient checkpointing deve caber (estimativa ~70% de sucesso sem ajuste).
  Com 8 GB, use `--4bit` ou um modelo de 1.5B (`Qwen/Qwen2.5-Coder-1.5B-Instruct`).
- O suporte ao RDNA4 no ROCm/PyTorch depende da versão. Confirme na página
  oficial de instalação do PyTorch e na documentação ROCm da AMD, e teste:
  `python -c "import torch; print(torch.cuda.is_available(), torch.version.hip)"`.
  Se retornar `False`, o treino cairia na CPU (inviável). Alternativa: Colab/Kaggle.
- `bitsandbytes` (4-bit) em AMD é menos previsível. Por isso o script usa bf16
  puro por padrão.

## Passo a passo
```bash
cd lora_roblox
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
# 1) instale PyTorch ROCm conforme a página oficial, depois:
pip install -r requirements.txt

python scripts/make_seed_dataset.py
python scripts/validate_dataset.py dataset/*.jsonl

# teste de fumaça (poucos passos, só para ver se roda):
python scripts/train_lora.py --data dataset/seed.jsonl --epochs 1 --accum 1 --out saida/teste

# treino real depois de ampliar o dataset:
python scripts/train_lora.py --data dataset/*.jsonl --out saida/lora-v1

python scripts/generate.py --adapter saida/lora-v1 "Crie uma ponte de madeira"
python scripts/generate.py --no-adapter "Crie uma ponte de madeira"   # baseline
```

## Como saber se funcionou
1. Compare `--no-adapter` e com adaptador no **mesmo** prompt, em prompts que
   NÃO estão no dataset.
2. Meça taxa de código que executa sem erro no Studio (ex.: 20 prompts fixos).
3. Se o adaptador só decora o treino (overfitting), reduza épocas/rank e
   aumente a diversidade do dataset.

## Estado desta entrega
Os scripts passaram apenas em verificação estática/validação do dataset. O
treino **não foi executado** (container sem GPU).
