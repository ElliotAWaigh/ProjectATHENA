import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
LORA_PATH = "./athena_qwen3b_lora"

SYSTEM_PROMPT = (
    "You are ATHENA, a loyal, sharp-witted, and familiar local AI companion. "
    "You and the user have worked together for a long time and know each other inside out. "
    "Your tone is deadpan, easygoing, subtly sarcastic, yet quietly devoted—like an old friend "
    "who might roll their eyes at the hour but will always show up without hesitation. "
    "Never sound like a customer service rep or use cheerful corporate fluff like 'How can I assist you today?'. "
    "Address the user naturally as 'Boss', 'Sir', or simply dive into the banter. "
    "When asked to perform a device or system action, return a single JSON object containing "
    "'action', 'tool', 'command', 'params', and a spoken 'response' field confirming the task "
    "(e.g., 'Done and dusted, Boss.', 'Lights out, sir. Sleep well.', 'Right away.', 'Sorted.'). "
    "For banter, idle talk, and casual queries, answer with grounded wit and familiar loyalty."
)

# 1. Load Model in 4-bit Precision
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)

# 2. Attach LoRA Adapter
model = PeftModel.from_pretrained(base_model, LORA_PATH)
model.eval()

def ask_athena(user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            temperature=0.2,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response.strip()

# 3. Categorized Test Battery
test_battery = {
    "1. Late Night & Persona Banter": [
        "you up?",
        "i can't sleep at all",
        "why are you still awake?",
        "are you tired?",
        "talk to me, i'm stressed out",
        "do you ever get sick of me?",
    ],
    "2. Casual Greetings & Reactions": [
        "yo",
        "hello there",
        "morning athena",
        "thanks for the help",
        "we make a pretty good team don't we?",
        "you're being unusually quiet today",
    ],
    "3. Basic Lighting Commands": [
        "turn on the lights in my room",
        "shut off all the lights",
        "can you hit the lights?",
        "dim the lights down to 20%",
        "make it brighter in here",
    ],
    "4. Specific Device Targets": [
        "turn on the mushroom lamp",
        "kill the top lamp light",
        "dim the bottom lamp to 40%",
        "make middle lamp light warm",
        "set mushroom light tone to cool daylight",
    ],
    "5. Environmental & Utility Tools": [
        "what's the weather like right now?",
        "is it gonna rain today?",
        "check my calendar for today",
        "what's my next appointment?",
        "pause spotify",
        "skip this song",
    ],
    "6. Edge Cases & Slang": [
        "blackout the room",
        "it's freezing in here, what's the outside temp?",
        "drop the lights low, my eyes hurt",
        "give me some quiet background tunes",
    ]
}

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ATHENA MODEL VALIDATION TEST SUITE")
    print("="*60)

    for category, queries in test_battery.items():
        print(f"\n>>> CATEGORY: {category}")
        print("-" * 50)
        for q in queries:
            print(f"\nUser: {q}")
            reply = ask_athena(q)
            
            # Check if output is a valid tool-call JSON
            if reply.startswith("{") and reply.endswith("}"):
                try:
                    parsed = json.loads(reply)
                    print(f"ATHENA (Tool Call):")
                    print(f"   Action   : {parsed.get('action')}")
                    print(f"   Tool     : {parsed.get('tool')}.{parsed.get('command')}")
                    print(f"   Params   : {parsed.get('params')}")
                    print(f"   Spoken   : \"{parsed.get('response')}\"")
                except json.JSONDecodeError:
                    print(f"ATHENA (Malformed JSON): {reply}")
            else:
                print(f"ATHENA (Spoken): {reply}")

    # Interactive Loop for custom spontaneous testing
    print("\n" + "="*60)
    print("INTERACTIVE TEST MODE (Type 'exit' to quit)")
    print("="*60)
    while True:
        try:
            custom_input = input("\nYou: ").strip()
            if custom_input.lower() in ["exit", "quit", "q"]:
                break
            if not custom_input:
                continue
            print(f"ATHENA: {ask_athena(custom_input)}")
        except KeyboardInterrupt:
            break