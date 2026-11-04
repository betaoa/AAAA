"""Treino LoRA (SFT) de um LLM de codigo para gerar Luau/Roblox.

Sem bitsandbytes por padrao: LoRA em bf16, mais seguro em GPU AMD (ROCm).
Use --4bit apenas se bitsandbytes funcionar no seu ambiente.

Exemplo:
    python scripts/train_lora.py --data dataset/seed.jsonl --out saida/lora-v1
"""
import argparse
import json
import random

import torch
from peft import LoraConfig, get_peft_model
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

IGNORE = -100


class ChatSFT(Dataset):
    """Mascara o prompt: a perda e calculada so na ultima resposta (assistant)."""

    def __init__(self, rows, tok, max_len):
        self.items = []
        skipped = 0
        for row in rows:
            msgs = row["messages"]
            prompt = tok.apply_chat_template(
                msgs[:-1], tokenize=False, add_generation_prompt=True
            )
            full = prompt + msgs[-1]["content"] + (tok.eos_token or "")
            p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
            f_ids = tok(full, add_special_tokens=False)["input_ids"]
            if len(f_ids) > max_len:
                skipped += 1
                continue
            labels = [IGNORE] * len(p_ids) + f_ids[len(p_ids):]
            self.items.append({"input_ids": f_ids, "labels": labels})
        print(f"exemplos usados={len(self.items)} descartados(>max_len)={skipped}")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def make_collator(pad_id):
    def collate(batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), pad_id, dtype=torch.long)
        lab = torch.full((len(batch), n), IGNORE, dtype=torch.long)
        att = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            k = len(b["input_ids"])
            ids[i, :k] = torch.tensor(b["input_ids"])
            lab[i, :k] = torch.tensor(b["labels"])
            att[i, :k] = 1
        return {"input_ids": ids, "labels": lab, "attention_mask": att}

    return collate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-3B-Instruct")
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--out", default="saida/lora-v1")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=16)
    ap.add_argument("--val-split", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--4bit", dest="four_bit", action="store_true")
    a = ap.parse_args()

    random.seed(a.seed)
    rows = []
    for p in a.data:
        rows += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    random.shuffle(rows)
    n_val = int(len(rows) * a.val_split)  # 0 se dataset pequeno
    val_rows, train_rows = rows[:n_val], rows[n_val:]

    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token

    kw = {"torch_dtype": torch.bfloat16}
    if a.four_bit:
        from transformers import BitsAndBytesConfig

        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            r=a.rank,
            lora_alpha=a.alpha,
            lora_dropout=0.05,
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()

    train_ds = ChatSFT(train_rows, tok, a.max_len)
    val_ds = ChatSFT(val_rows, tok, a.max_len) if val_rows else None

    args = TrainingArguments(
        output_dir=a.out,
        per_device_train_batch_size=a.batch,
        per_device_eval_batch_size=a.batch,
        gradient_accumulation_steps=a.accum,
        num_train_epochs=a.epochs,
        learning_rate=a.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        bf16=True,
        logging_steps=5,
        eval_strategy="epoch" if val_ds else "no",
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
        remove_unused_columns=False,
        seed=a.seed,
    )
    Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=make_collator(tok.pad_token_id),
    ).train()

    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    print(f"adaptador salvo em {a.out}")


if __name__ == "__main__":
    main()
