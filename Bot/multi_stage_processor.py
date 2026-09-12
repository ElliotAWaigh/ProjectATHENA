import asyncio
import json
from pathlib import Path
import re
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from tool_registry import ToolRegistry

# Path resolution:
# BOT_DIR = 00ATHENA/ProjectATHENA/Bot
# PROJECT_ROOT = 00ATHENA/ProjectATHENA
# WORKSPACE_ROOT = 00ATHENA (where athena_qwen3b_lora is located)
BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BOT_DIR.parent

LORA_PATH = str(PROJECT_ROOT / "athena_qwen3b_lora")

WORKSPACE_ROOT = PROJECT_ROOT.parent

DEFAULT_TOOLS_MANIFEST = str(BOT_DIR / "config" / "tools.json")
BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

# Direct path to your trained adapter in 00ATHENA
LORA_PATH = str(WORKSPACE_ROOT / "athena_qwen3b_lora")

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


class MultiStageProcessor:
    def __init__(self, tools_manifest=DEFAULT_TOOLS_MANIFEST):
        print("[MSP] 🧠 Loading ToolRegistry...")
        self.tool_registry = ToolRegistry(tools_manifest)

        print(f"[MSP] 🚀 Initializing Qwen 2.5 3B with ATHENA LoRA adapter from {LORA_PATH}...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL_ID,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
        )

        self.model = PeftModel.from_pretrained(base_model, LORA_PATH)
        self.model.eval()
        print("[MSP] ✅ ATHENA local neural pipeline ready.")

    def _query_llm(self, user_input: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.2,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        reply = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return reply.strip()

    async def _maybe_await(self, func, **kwargs):
        res = func(**kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res

    def process_query(self, user_input: str):
        if not user_input.strip():
            return "ATHENA: I didn't catch that.", False

        raw_reply = self._query_llm(user_input)

        # 1. Check if output is a JSON tool-call
        json_match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
        if json_match:
            try:
                payload = json.loads(json_match.group(0))
                if payload.get("action") == "call_tool":
                    tool = payload.get("tool")
                    cmd = payload.get("command")
                    params = payload.get("params", {})
                    spoken_response = payload.get("response", "On it, Boss.")

                    # Execute the underlying python function
                    exec_result = self._execute_tool(tool, cmd, params)
                    
                    # Return spoken companion confirmation
                    return f"ATHENA: {spoken_response}", False
            except Exception as e:
                print(f"[MSP] ⚠️ JSON parse/execution error: {e}")

        # 2. Conversational response (banter, idle talk)
        return f"ATHENA: {raw_reply}", False

    def _execute_tool(self, tool_name: str, cmd: str, params: dict):
        meta = self.tool_registry.get_command_meta(tool_name, cmd)
        if not meta:
            print(f"[MSP] ⚠️ Tool command '{tool_name}.{cmd}' not found in registry.")
            return None

        func, _, expected_params, defaults = meta
        
        # Merge default values if missing
        merged_params = {**(defaults or {}), **(params or {})}
        
        # Filter strictly to expected parameters of the tool function
        filtered_params = {k: v for k, v in merged_params.items() if k in expected_params}

        try:
            result = asyncio.run(self._maybe_await(func, **filtered_params))
            return result
        except Exception as e:
            print(f"[MSP] ❌ Error executing {tool_name}.{cmd}: {e}")
            return None