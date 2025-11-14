import importlib
import json
import os
import traceback


class ToolRegistry:
    """
    Loads tools from a manifest (config/tools.json) that maps intent -> module path.
    Each tool must expose a TOOL_SPEC = {
        "intent": "...",
        "description": "...",
        "commands": {
            "command_name": {
                "examples": [...],
                "params": [...],          # params expected by the function
                "defaults": {...},        # <-- NEW: default values if not provided
                "function": "func_name"
            }, ...
        }
    }
    """
    def __init__(self, tools_manifest="config/tools.json"):
        self.manifest_path = tools_manifest
        self.tools = {}      # intent -> module
        # commands[(intent, cmd)] = (func, examples, params, defaults)
        self.commands = {}
        self._load_from_manifest()

    # ------------------------------------------------------------------
    def _load_from_manifest(self):
        if not os.path.isfile(self.manifest_path):
            print(f"[ToolRegistry] ⚠️ tools.json not found at {self.manifest_path}")
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"[ToolRegistry] ❌ Failed to parse tools.json: {e}")
            return

        loaded_tools = 0
        loaded_cmds = 0

        for intent, module_path in manifest.items():
            try:
                module = importlib.import_module(module_path)
            except Exception as e:
                print(f"[ToolRegistry] ❌ Failed to import {module_path}: {e}")
                traceback.print_exc()
                continue

            spec = getattr(module, "TOOL_SPEC", None)
            if not spec or "commands" not in spec:
                print(f"[ToolRegistry] ⚠️ TOOL_SPEC missing/invalid in {module_path}")
                continue

            self.tools[intent] = module
            loaded_tools += 1

            for cmd, meta in spec["commands"].items():
                func_name = meta.get("function")
                examples = meta.get("examples", [])
                params = meta.get("params", [])  # list of param names
                defaults = meta.get("defaults", {})  # NEW field

                if not func_name or not hasattr(module, func_name):
                    print(f"[ToolRegistry] ⚠️ Missing function for {intent}.{cmd}")
                    continue

                func = getattr(module, func_name)
                self.commands[(intent, cmd)] = (func, examples, params, defaults)
                loaded_cmds += 1

            print(f"[ToolRegistry] ✅ Registered tool: {intent}")

        print(f"[ToolRegistry DEBUG] Loaded {loaded_tools} tools and {loaded_cmds} commands.")

    # ------------------------------------------------------------------
    def get_all_examples(self):
        """
        Returns {intent: {cmd: [examples...]}}
        """
        examples_by_intent = {}
        for (intent, cmd), (func, examples, params, defaults) in self.commands.items():
            examples_by_intent.setdefault(intent, {})[cmd] = examples
        return examples_by_intent

    def get_tool(self, intent):
        return self.tools.get(intent)

    def get_command_meta(self, intent, cmd):
        """
        Returns (func, examples, params, defaults) or None.
        """
        return self.commands.get((intent, cmd))
