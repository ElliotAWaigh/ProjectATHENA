import asyncio
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tool_registry import ToolRegistry
from entity_extractor import extract_entities  # use your existing extractor


class MultiStageProcessor:
    def __init__(self, tools_manifest="config/tools.json", direct_threshold=0.65):
        self.tool_registry = ToolRegistry(tools_manifest)
        self.threshold = direct_threshold
        self.vectorizer = None
        self.matrix = None
        self.index = []
        self.context = None  # store ongoing conversation state
        self._build_command_tfidf()

    # ----------------------------- TF-IDF SETUP -----------------------------
    def _prep(self, text):
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def _build_command_tfidf(self):
        """Builds TF-IDF model from TOOL_SPEC examples."""
        all_examples = []
        self.index = []

        examples_dict = self.tool_registry.get_all_examples()
        for intent, cmds in examples_dict.items():
            for cmd, examples in cmds.items():
                func, _ = self.tool_registry.commands[(intent, cmd)]
                for ex in examples:
                    all_examples.append(self._prep(ex))
                    self.index.append((intent, cmd, func))

        if not all_examples:
            print("[MSP] ⚠️ No command examples found. Processor disabled.")
            return

        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(all_examples)
        print(f"[MSP] ✅ Loaded {len(all_examples)} example commands from tools.")

    # ----------------------------- MATCHING -----------------------------
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

    # ----------------------------- CONTEXT + EXECUTION -----------------------------
    def process_query(self, user_input: str):
        text = user_input.lower().strip()

        # Case 1 — existing context waiting for missing parameters
        if self.context:
            pending = self.context
            params = pending["params"]

            # try to extract entities or infer values
            new_entities = extract_entities(text)
            params.update(new_entities)

            still_missing = [p for p in pending["missing"] if p not in params or params[p] is None]
            if not still_missing or text in ["that's all", "thats all", "done"]:
                # Execute now
                result = self._execute_intent(pending["intent"], pending["cmd"], params)
                self.context = None
                return result
            else:
                self.context["missing"] = still_missing
                return f"ATHENA: Do you have info for {', '.join(still_missing)}? If not, say 'that's all'.", True

        # Case 2 — normal processing
        intent, cmd, func, score = self._best_match(user_input)
        if not intent or score < self.threshold:
            return "ATHENA: I'm not sure what you mean. Can you rephrase?", True

        module = self.tool_registry.get_tool(intent)
        params = {}
        if hasattr(module, "resolve_params"):
            try:
                params = module.resolve_params(user_input)
            except Exception as e:
                print(f"[MSP] ⚠️ Param resolution failed: {e}")

        # also merge entities from extractor
        entities = extract_entities(user_input)
        params.update({k: v for k, v in entities.items() if v is not None})

        # get expected params from TOOL_SPEC
        spec = getattr(module, "TOOL_SPEC", {}).get("commands", {}).get(cmd, {})
        required_params = spec.get("params", [])

        missing = [p for p in required_params if p not in params or params[p] is None]

        if missing:
            self.context = {
                "intent": intent,
                "cmd": cmd,
                "params": params,
                "missing": missing,
            }
            return f"ATHENA: I need more information — required: {', '.join(missing)}.", True

        # all info present — execute
        result = self._execute_intent(intent, cmd, params)
        return result

    # ----------------------------- EXECUTION -----------------------------
    def _execute_intent(self, intent, cmd, params):
        try:
            func, _ = self.tool_registry.commands[(intent, cmd)]
            result = asyncio.run(self._maybe_await(func, **params))
            return f"ATHENA: {result}", False
        except Exception as e:
            return f"ATHENA: Error executing {cmd}: {e}", False
