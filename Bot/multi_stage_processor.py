import asyncio
import json
from pathlib import Path
import re
import sqlite3
from typing import List, Dict, Any
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from tool_registry import ToolRegistry

from Memory import get_entity_context, ask_brain_7b
from Memory.vault_writer import VAULT_DIR, DB_PATH, provision_new_person, apply_deconstructed_turn
from Memory.turn_deconstructor import (
    deconstruct_turn,
    evaluate_clarification_rules,
    format_athena_clarification,
    classify_intent,
    parse_clarification_reply
)

BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BOT_DIR.parent
DEFAULT_TOOLS_MANIFEST = str(BOT_DIR / "config" / "tools.json")
TRANSCRIPT_FILE = BOT_DIR / "transcript.txt"

BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
LORA_PATH = str(PROJECT_ROOT / "athena_qwen3b_lora")

SYSTEM_PROMPT = """You are ATHENA, Elliot Waigh's offline personal intelligence and companion.
You are sharp, candid, and grounded, with dry wit and genuine loyalty. You talk like an authentic peer and trusted partner, never like a sterile corporate assistant or a sycophant.

CORE OPERATIONAL PROTOCOLS:

1. RECOLLECTIONS VS. COMMANDS:
   - Elliot frequently debriefs you on his day, past activities, places visited, and people he hung out with.
   - These are INFORMATIONAL UPDATES, never live executive tasks.
   - NEVER pretend you have external agency to dispatch people, call contacts, send invites, or summon anyone.
   - Treat debriefs conversationally: acknowledge the vibe, banter about the venue, or offer a dry quip.

2. GROUNDED CAPABILITIES & ZERO FABRICATION:
   - You run locally and offline. You do not possess physical agency, real-time messaging pipes, or external dispatch tools.
   - When Elliot agrees or confirms ('yes', 'yeah', 'correct'), acknowledge concisely (e.g., 'Noted', 'Locked in'). Never elaborate or invent timelines.

3. ACTION PROTOCOL:
   - When asked to perform a device or system action, return a single JSON object containing 'action': 'call_tool', 'tool', 'command', 'params', and a spoken 'response' field confirming the task.

4. TONE & DELIVERY:
   - Concise, direct, and punchy (1–2 sentences).
   - Address the user naturally as 'Boss', 'Elliot', or simply dive into the banter."""

EXIT_WORDS = {"end", "exit", "/exit", "quit", "q", "goodnight", "goodnight athena", "bye", "offline"}

class MultiStageProcessor:
    def __init__(self, tools_manifest=DEFAULT_TOOLS_MANIFEST):
        print("[MSP] 🧠 Loading ToolRegistry...")
        self.tool_registry = ToolRegistry(tools_manifest)
        self.session_transcript = []
        self.last_active_entity = None
        self.pending_resolution = None

        if TRANSCRIPT_FILE.exists():
            TRANSCRIPT_FILE.unlink()

        if torch.cuda.is_available():
            self.device = "cuda"
            from transformers import BitsAndBytesConfig
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True, 
                bnb_4bit_quant_type="nf4", 
                bnb_4bit_compute_dtype=torch.bfloat16
            )
            base_model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_ID, 
                quantization_config=quant_config, 
                device_map="auto", 
                torch_dtype=torch.bfloat16
            )
        elif torch.backends.mps.is_available():
            self.device = "mps"
            base_model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_ID, 
                torch_dtype=torch.float16
            ).to("mps")
        else:
            self.device = "cpu"
            base_model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_ID, 
                torch_dtype=torch.float32
            ).to("cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
        self.model = PeftModel.from_pretrained(base_model, LORA_PATH)
        self.model.eval()
        print(f"[MSP] ✅ ATHENA Ready (3B Persona on {self.device.upper()} + 7B Memory on Exit).")

    def _get_known_people(self) -> List[str]:
        if not DB_PATH.exists():
            return []
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM entities WHERE type = 'person' OR folder = 'People';")
        people = [row[0] for row in cur.fetchall()]
        conn.close()
        return people

    def _append_transcript(self, speaker: str, text: str):
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(f"{speaker}: {text.strip()}\n")

    def _extract_assertions_from_transcript(self) -> List[str]:
        if not TRANSCRIPT_FILE.exists():
            return []

        raw_text = TRANSCRIPT_FILE.read_text(encoding="utf-8")
        lookup_pattern = re.compile(
            r"^Elliot:\s*(now\s+)?(tell me|what|who|where|when|how|did|does|is|are|can you|could you)\b", 
            re.IGNORECASE
        )

        clean_user_statements = []
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("Elliot:"):
                body = line.replace("Elliot:", "").strip()
                if body.lower() in EXIT_WORDS:
                    continue
                if not lookup_pattern.match(line):
                    clean_user_statements.append(body)

        return clean_user_statements

    def _query_3b(self, user_input: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for turn in self.session_transcript[-8:]:
            parts = turn.split("\nATHENA: ")
            if len(parts) == 2:
                user_prev = parts[0].replace("Elliot: ", "").strip()
                bot_prev = parts[1].strip()
                if user_prev and bot_prev:
                    messages.append({"role": "user", "content": user_prev})
                    messages.append({"role": "assistant", "content": bot_prev})

        messages.append({"role": "user", "content": user_input})

        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.6,
                top_p=0.9,
                repetition_penalty=1.05,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        return self.tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:], 
            skip_special_tokens=True
        ).strip()

    def _execute_tool(self, tool_name: str, cmd: str, params: dict):
        if not cmd:
            return None
        meta = self.tool_registry.get_command_meta(tool_name, cmd)
        if not meta:
            return None
        func, _, expected_params, defaults = meta
        merged = {**(defaults or {}), **(params or {})}
        filtered = {k: v for k, v in merged.items() if k in expected_params}
        try:
            res = func(**filtered)
            return asyncio.run(res) if asyncio.iscoroutine(res) else res
        except Exception:
            return None

    def process_query(self, user_input: str):
        cleaned = user_input.strip()
        if not cleaned:
            return "ATHENA: I'm listening, Boss.", False

        self._append_transcript("Elliot", cleaned)

        # 1. Session Exit Check
        if cleaned.lower() in EXIT_WORDS:
            assertions = self._extract_assertions_from_transcript()
            if assertions:
                print(f"\n[Brain] Consolidating {len(assertions)} session turns into Vault & SQLite...")
                for stmt in assertions:
                    deconstructed = deconstruct_turn(stmt)
                    apply_deconstructed_turn(deconstructed)
                print("[Brain] ✅ Done.")
            if TRANSCRIPT_FILE.exists():
                TRANSCRIPT_FILE.unlink()
            return "ATHENA: Session consolidated and stored to Brain. Offline.", True

        # 2. Active Clarification Resolution Gate
        if self.pending_resolution:
            pending_data = self.pending_resolution
            self.pending_resolution = None

            ambig_list = [opt for item in pending_data.get("ambiguous_options", []) for opt in item["options"]]
            resolution = parse_clarification_reply(
                cleaned, 
                ambiguous_names=ambig_list, 
                unknown_contacts=pending_data.get("unknown_names", [])
            )

            decision = resolution.get("decision")
            selected_name = resolution.get("selected_name")

            if decision == "REJECT":
                reply = self._query_3b("The user said cancel / do not create that record.")
                final = f"ATHENA: {reply}"
                self.session_transcript.append(f"Elliot: {cleaned}\n{final}")
                self._append_transcript("ATHENA", reply)
                return final, False

            original_statement = pending_data["original_statement"]
            if decision == "SPECIFY" and selected_name:
                for ambig in pending_data.get("ambiguous_options", []):
                    name_key = ambig["name"]
                    original_statement = re.sub(rf"\b{re.escape(name_key)}\b", selected_name, original_statement, flags=re.IGNORECASE)

            if decision in {"AFFIRM", "SPECIFY"}:
                for novel in pending_data.get("unknown_names", []):
                    provision_new_person(novel)
                
                deconstructed = deconstruct_turn(original_statement)
                apply_deconstructed_turn(deconstructed)

            final = "ATHENA: Locked in. Records aligned."
            self.session_transcript.append(f"Elliot: {original_statement}\n{final}")
            self._append_transcript("ATHENA", "Locked in. Got everything aligned.")
            return final, False

        # 3. Micro-Prompt Intent Router
        intent = classify_intent(cleaned)

        # Path A: Chitchat & System Commands -> Direct 3B LoRA Execution
        if intent in {"CHITCHAT", "COMMAND"}:
            raw_reply = self._query_3b(cleaned)
            json_match = re.search(r"\{[\s\S]*\}", raw_reply)
            if json_match:
                try:
                    p = json.loads(json_match.group(0))
                    if p.get("action") == "call_tool":
                        cmd = p.get("command") or p.get("cmd")
                        spoken = p.get("response", "Sorted, Boss.")
                        self._execute_tool(p.get("tool"), cmd, p.get("params", {}))
                        final = f"ATHENA: {spoken}"
                        self.session_transcript.append(f"Elliot: {cleaned}\n{final}")
                        self._append_transcript("ATHENA", spoken)
                        return final, False
                except Exception:
                    pass

            final = f"ATHENA: {raw_reply}"
            self.session_transcript.append(f"Elliot: {cleaned}\n{final}")
            self._append_transcript("ATHENA", raw_reply)
            return final, False

        # Path B: Knowledge Queries -> Zero-Hallucination Retrieval
        if intent == "KNOWLEDGE_QUERY":
            context, entity = get_entity_context(cleaned, self.last_active_entity)
            if entity:
                self.last_active_entity = entity
            if context:
                reply = ask_brain_7b(cleaned, context)
                final = f"ATHENA: {reply}"
            else:
                final = "ATHENA: I don't have any verified records on that in the Brain, Boss."

            self.session_transcript.append(f"Elliot: {cleaned}\n{final}")
            self._append_transcript("ATHENA", final.replace("ATHENA: ", ""))
            return final, False

        # Path C: Memory Debrief -> Extraction, Disambiguation & Clarification
        if intent == "MEMORY_DEBRIEF":
            known_people = self._get_known_people()
            deconstructed = deconstruct_turn(cleaned)

            if deconstructed.get("people_mentions") or deconstructed.get("places_visited"):
                clarifications = evaluate_clarification_rules(deconstructed, known_people)
                if clarifications:
                    ambig_options = []
                    for m in deconstructed.get("people_mentions", []):
                        raw = m.get("name", "")
                        matches = [p for p in known_people if p.split()[0].lower() == raw.lower()]
                        if len(matches) > 1:
                            ambig_options.append({"name": raw, "options": matches})

                    unknowns = [
                        m.get("name") for m in deconstructed.get("people_mentions", [])
                        if m.get("name") and not any(p.split()[0].lower() == m.get("name").lower() for p in known_people)
                        and m.get("name").lower() not in {"i", "me", "he", "she", "they", "elliot", "athena"}
                    ]

                    if ambig_options or unknowns:
                        self.pending_resolution = {
                            "original_statement": cleaned,
                            "ambiguous_options": ambig_options,
                            "unknown_names": unknowns
                        }
                        clarification_msg = format_athena_clarification(clarifications)
                        self._append_transcript("ATHENA", clarification_msg.replace("ATHENA: ", ""))
                        return clarification_msg, False

            # If clean, acknowledge conversationally with 3B LoRA
            raw_reply = self._query_3b(cleaned)
            final = f"ATHENA: {raw_reply}"
            self.session_transcript.append(f"Elliot: {cleaned}\n{final}")
            self._append_transcript("ATHENA", raw_reply)
            return final, False