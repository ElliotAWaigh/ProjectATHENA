import asyncio
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tool_registry import ToolRegistry

# If you already have a richer extractor, import and use it here
try:
    from entity_extractor import extract_entities
except Exception:
    def extract_entities(_text: str):
        return {}


class MultiStageProcessor:
    def __init__(self, tools_manifest="config/tools.json", direct_threshold=0.65):
        self.tool_registry = ToolRegistry(tools_manifest)
        self.threshold = direct_threshold
        self.vectorizer = None
        self.matrix = None
        self.index = []       # [(intent, cmd, func)]
        self._build_command_tfidf()

        # simple slot-filling memory (optional; still works as before)
        self.context = None

    # ---------------- TF-IDF ----------------
    def _prep(self, text):
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def _build_command_tfidf(self):
        all_examples = []
        self.index = []

        examples_dict = self.tool_registry.get_all_examples()
        for intent, cmds in examples_dict.items():
            for cmd, examples in cmds.items():
                meta = self.tool_registry.get_command_meta(intent, cmd)
                if not meta:
                    continue
                func, example_list, params, defaults = meta
                for ex in example_list:
                    all_examples.append(self._prep(ex))
                    self.index.append((intent, cmd, func))

        if not all_examples:
            print("[MSP] ⚠️ No command examples found. Processor disabled.")
            return

        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(all_examples)
        print(f"[MSP] ✅ Loaded {len(all_examples)} example commands from tools.")

    def _best_match(self, text):
        if not text.strip() or self.matrix is None or not self.matrix.shape[0]:
            return None, None, None, 0.0
        x = self.vectorizer.transform([self._prep(text)])
        sims = cosine_similarity(x, self.matrix).flatten()
        best_idx = int(np.argmax(sims))
        intent, cmd, func = self.index[best_idx]
        return intent, cmd, func, float(sims[best_idx])

    async def _maybe_await(self, func, **kwargs):
        res = func(**kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res

    # ------------- PARAM MERGE LOGIC (defaults!) -------------
    def _merge_params(self, intent, cmd, user_text):
        """
        Merge params in this order (later wins):
          1) defaults from TOOL_SPEC.commands[cmd].defaults
          2) tool.resolve_params(user_text) if available
          3) global extract_entities(user_text)
        """
        module = self.tool_registry.get_tool(intent)
        defaults = {}
        resolved = {}
        entities = {}

        meta = self.tool_registry.get_command_meta(intent, cmd)
        _, _, params_list, defaults = meta if meta else (None, None, [], {})

        if hasattr(module, "resolve_params"):
            try:
                resolved = module.resolve_params(user_text) or {}
            except Exception as e:
                print(f"[MSP] ⚠️ resolve_params failed for {intent}.{cmd}: {e}")
                resolved = {}

        try:
            entities = extract_entities(user_text) or {}
        except Exception as e:
            print(f"[MSP] ⚠️ extract_entities failed: {e}")
            entities = {}

        # Merge: defaults → resolved → entities (explicit > default)
        merged = {**(defaults or {}), **(resolved or {}), **(entities or {})}
        return merged, params_list

    # ------------- CONTEXT + EXECUTION -------------
    def process_query(self, user_input: str):
        text = user_input.lower().strip()

        # If we were waiting for missing params, keep filling:
        if self.context:
            pending = self.context
            prev_params = pending["params"]
            updates, params_list = self._merge_params(pending["intent"], pending["cmd"], text)
            merged = {**prev_params, **updates}

            missing_after = [p for p in params_list if merged.get(p) is None]
            if not missing_after or text in ("that's all", "thats all", "done"):
                result = self._execute_intent(pending["intent"], pending["cmd"], merged)
                self.context = None
                return result
            else:
                self.context["params"] = merged
                self.context["missing"] = missing_after
                return f"ATHENA: Do you have info for {', '.join(missing_after)}? If not, say 'that's all'.", True

        # Normal path
        intent, cmd, func, score = self._best_match(user_input)
        if not intent or score < self.threshold:
            return "ATHENA: I'm not sure what you mean. Can you rephrase?", True

        # Build params with defaults support
        params, params_list = self._merge_params(intent, cmd, user_input)

        # A param is considered "required" only if it's listed and not provided by defaults
        missing = [p for p in params_list if params.get(p) is None]
        if missing:
            # store context to fill later
            self.context = {"intent": intent, "cmd": cmd, "params": params, "missing": missing}
            # declare missing ones
            return f"ATHENA: I need more information — required: {', '.join(missing)}.", True

        # execute immediately
        return self._execute_intent(intent, cmd, params)

    def _execute_intent(self, intent, cmd, params):
        try:
            func, _, _, _ = self.tool_registry.get_command_meta(intent, cmd)
            result = asyncio.run(self._maybe_await(func, **params))
            return f"ATHENA: {result}", False
        except Exception as e:
            return f"ATHENA: Error executing {cmd}: {e}", False
