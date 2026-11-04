"""Testa o adaptador treinado.

    python scripts/generate.py --adapter saida/lora-v1 "Crie uma ponte de madeira"
Use --no-adapter para comparar com o modelo base (mesmo prompt).
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

SYSTEM = (
    "Voce e um assistente de Roblox Studio. Responda somente com codigo Luau "
    "valido, em um unico bloco, pronto para rodar em um Script do servidor."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-3B-Instruct")
    ap.add_argument("--adapter", default="saida/lora-v1")
    ap.add_argument("--no-adapter", action="store_true")
    ap.add_argument("--max-new", type=int, default=800)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.bfloat16)
    if not a.no_adapter:
        model = PeftModel.from_pretrained(model, a.adapter)
    model = model.to("cuda" if torch.cuda.is_available() else "cpu").eval()

    text = tok.apply_chat_template(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": a.prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )
    ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=a.max_new, do_sample=True,
                             temperature=0.4, top_p=0.9)
    print(tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True))


if __name__ == "__main__":
    main()
