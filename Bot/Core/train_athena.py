import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
OUTPUT_DIR = "./athena_qwen3b_lora"

# 1. 4-bit Quantization Configuration (fits easily within 8GB VRAM)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,  # Changed from float16 to bfloat16
    bnb_4bit_use_double_quant=True,
)

# 2. Load Base Model & Tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,  # Changed from float16 to bfloat16
)

# 3. LoRA Configuration
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# 4. Dataset
dataset = load_dataset("json", data_files="ProjectATHENA/Bot/Core/athena_train.jsonl")

# 5. Training Arguments
training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    logging_steps=5,
    save_strategy="epoch",
    bf16=True,   # Changed to True
    fp16=False,  # Explicitly disable fp16
    max_length=512,
)

# 6. Trainer
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset["train"],
    peft_config=peft_config,
    args=training_args,
)

if __name__ == "__main__":
    print("Starting QLoRA training on RTX 3060 Ti...")
    trainer.train()
    trainer.model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Training complete! Adapter saved to {OUTPUT_DIR}")