import os
import sys
import json
import importlib
import traceback


class ToolRegistry:
    def __init__(self, tools_manifest="config/tools.json"):
        """
        Loads tools defined in config/tools.json.
        Supports fallback to ../config/tools.json automatically.
        """
        self.tools_manifest = self._resolve_manifest_path(tools_manifest)
        self.tools = {}
        self.commands = {}

        self._load_manifest()

    # ------------------------------------------------------------------
    def _resolve_manifest_path(self, relative_path):
        """Search for config/tools.json in multiple likely locations."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(current_dir, relative_path)
        parent_path = os.path.join(os.path.dirname(current_dir), relative_path)

        if os.path.exists(local_path):
            return local_path
        elif os.path.exists(parent_path):
            return parent_path
        else:
            print(f"[ToolRegistry] ⚠️ tools.json not found in expected paths:\n  - {local_path}\n  - {parent_path}")
            return local_path  # keep default for safety

    # ------------------------------------------------------------------
    def _load_manifest(self):
        if not os.path.exists(self.tools_manifest):
            print(f"[ToolRegistry] ⚠️ tools.json not found at {self.tools_manifest}")
            return

        try:
            with open(self.tools_manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"[ToolRegistry] ❌ Failed to read tools.json: {e}")
            return

        # Ensure Tools folder is importable
        current_dir = os.path.dirname(os.path.abspath(__file__))
        tools_path = os.path.join(current_dir, "Tools")
        if tools_path not in sys.path:
            sys.path.append(tools_path)

        for intent, module_path in manifest.items():
            if not module_path.startswith("Tools."):
                module_path = f"Tools.{module_path}"

            try:
                module = importlib.import_module(module_path)
            except Exception as e:
                print(f"[ToolRegistry] ❌ Failed to import {module_path}: {e}")
                traceback.print_exc()
                continue

            if not hasattr(module, "TOOL_SPEC"):
                print(f"[ToolRegistry] ⚠️ No TOOL_SPEC found in {module_path}")
                continue

            spec = getattr(module, "TOOL_SPEC", None)
            if not spec or "commands" not in spec:
                print(f"[ToolRegistry] ⚠️ Invalid TOOL_SPEC in {module_path}")
                continue

            self.tools[intent] = module

            for cmd, info in spec["commands"].items():
                func_name = info.get("function")
                examples = info.get("examples", [])
                if not func_name or not hasattr(module, func_name):
                    print(f"[ToolRegistry] ⚠️ Missing function for {intent}.{cmd}")
                    continue

                func = getattr(module, func_name)
                self.commands[(intent, cmd)] = (func, examples)

            print(f"[ToolRegistry] ✅ Registered tool: {intent}")

        print(f"[ToolRegistry DEBUG] Loaded {len(self.tools)} tools and {len(self.commands)} commands.")

    # ------------------------------------------------------------------
    def get_all_examples(self):
        """Return {intent: {cmd: [examples...]}} for TF-IDF training."""
        examples_by_intent = {}
        for (intent, cmd), (func, examples) in self.commands.items():
            examples_by_intent.setdefault(intent, {})[cmd] = examples
        return examples_by_intent

    def get_tool(self, intent):
        return self.tools.get(intent)
