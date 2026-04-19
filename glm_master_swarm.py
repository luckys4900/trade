#!/usr/bin/env python3
"""
Agent Teams - Master (GLM5.1) + Dynamic Sub-Agents (Ollama + OpenRouter + Z.AI)
Uses OpenAI Swarm framework
"""

import asyncio
import json
import os
import urllib.request
from typing import Dict, List, Optional
from dotenv import load_dotenv
from swarm import Swarm, Agent
from openai import OpenAI

load_dotenv()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")

MASTER_MODEL = "glm-5.1"

OPENROUTER_FREE_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
]

ZAI_MODELS = [
    {"id": "glm-4", "name": "GLM-4", "provider": "Z.AI"},
    {"id": "glm-4-plus", "name": "GLM-4 Plus", "provider": "Z.AI"},
    {"id": "glm-4-0520", "name": "GLM-4 0520", "provider": "Z.AI"},
    {"id": "glm-4-flash", "name": "GLM-4 Flash", "provider": "Z.AI"},
    {"id": "glm-4.7", "name": "GLM-4.7", "provider": "Z.AI"},
    {"id": "glm-5.1", "name": "GLM-5.1", "provider": "Z.AI"},
]

ROLE_PRESETS = {
    "1": ("analyzer", "Fast analysis: syntax check, data processing, simple review."),
    "2": ("coder", "Code generation: write code, generate tests, create scripts."),
    "3": ("reviewer", "Deep review: security check, best practices, refactoring."),
    "4": (
        "researcher",
        "Research: investigate topics, summarize findings, compare options.",
    ),
    "5": ("writer", "Writing: documentation, explanations, reports."),
}


def make_ollama_client():
    return OpenAI(base_url=f"{OLLAMA_BASE_URL}/v1", api_key="ollama")


def make_openrouter_client():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def make_zai_client():
    return OpenAI(
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key=ZAI_API_KEY,
    )


def get_ollama_models() -> List[str]:
    try:
        r = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags")
        d = json.loads(r.read())
        return [m["name"] for m in d.get("models", [])]
    except Exception:
        return []


def get_openrouter_models() -> List[Dict[str, str]]:
    if not OPENROUTER_API_KEY:
        return []
    try:
        client = make_openrouter_client()
        response = client.models.list()
        models = []
        for m in response.data:
            model_id = m.id
            is_free = ":free" in model_id
            models.append(
                {
                    "id": model_id,
                    "name": model_id.split("/")[-1],
                    "full_id": model_id,
                    "is_free": is_free,
                    "provider": "OpenRouter",
                }
            )
        return sorted(models, key=lambda x: (not x["is_free"], x["name"]))
    except Exception as e:
        print(f"  [WARNING] Could not fetch OpenRouter models: {e}")
        return []


class AgentTeams:
    def __init__(self):
        self.ollama_client = make_ollama_client()
        self.openrouter_client = (
            make_openrouter_client() if OPENROUTER_API_KEY else None
        )
        self.zai_client = make_zai_client() if ZAI_API_KEY else None

        self.ollama_models = get_ollama_models()
        self.openrouter_models = get_openrouter_models()
        self.zai_models = ZAI_MODELS if ZAI_API_KEY else []

        # Set default env for master (Z.AI for GLM5.1)
        self.default_api_key = os.environ.get("OPENAI_API_KEY")
        self.default_base_url = os.environ.get("OPENAI_BASE_URL")
        os.environ["OPENAI_API_KEY"] = ZAI_API_KEY
        os.environ["OPENAI_BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"

        # Initialize Swarm AFTER setting env vars
        self.swarm = Swarm()

        # Master agent - use GLM5.1 via Z.AI
        self.master_agent = Agent(
            name="Master",
            instructions=(
                "You are the Master AI agent. You coordinate tasks.\n"
                "When given a task, analyze it and respond directly.\n"
                "Respond in the same language as the user."
            ),
            model=MASTER_MODEL,
        )

    def _get_env_for_model(self, model: str) -> tuple:
        if model in [m["id"] for m in self.zai_models]:
            return ZAI_API_KEY, "https://open.bigmodel.cn/api/paas/v4"
        if "/" in model:
            return OPENROUTER_API_KEY, "https://openrouter.ai/api/v1"
        return "ollama", f"{OLLAMA_BASE_URL}/v1"

    def _create_sub_agent(self, model: str, role_name: str, role_desc: str) -> Agent:
        return Agent(
            name=role_name.capitalize(),
            instructions=(
                f"You are a {role_name} agent.\n"
                f"Role: {role_desc}\n"
                "Respond in the same language as the user."
            ),
            model=model,
        )

    def run_master(self, prompt: str) -> str:
        # Set environment variable for Z.AI (GLM5.1)
        old_api_key = os.environ.get("OPENAI_API_KEY")
        old_base_url = os.environ.get("OPENAI_BASE_URL")

        os.environ["OPENAI_API_KEY"] = ZAI_API_KEY
        os.environ["OPENAI_BASE_URL"] = "https://open.bigmodel.cn/api/paas/v4"

        try:
            response = self.swarm.run(
                agent=self.master_agent,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.messages[-1]["content"]
        finally:
            if old_api_key is not None:
                os.environ["OPENAI_API_KEY"] = old_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if old_base_url is not None:
                os.environ["OPENAI_BASE_URL"] = old_base_url
            else:
                os.environ.pop("OPENAI_BASE_URL", None)

    def run_single_agent(
        self, model: str, role_name: str, role_desc: str, task: str
    ) -> str:
        agent = self._create_sub_agent(model, role_name, role_desc)
        api_key, base_url = self._get_env_for_model(model)

        old_api_key = os.environ.get("OPENAI_API_KEY")
        old_base_url = os.environ.get("OPENAI_BASE_URL")
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url

        try:
            response = self.swarm.run(
                agent=agent,
                messages=[{"role": "user", "content": task}],
            )
            return response.messages[-1]["content"]
        finally:
            if old_api_key is not None:
                os.environ["OPENAI_API_KEY"] = old_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if old_base_url is not None:
                os.environ["OPENAI_BASE_URL"] = old_base_url
            else:
                os.environ.pop("OPENAI_BASE_URL", None)

    async def run_parallel(self, agents_config: list, task: str) -> Dict[str, str]:
        async def _exec(cfg):
            agent = self._create_sub_agent(cfg["model"], cfg["role"], cfg["desc"])
            api_key, base_url = self._get_env_for_model(cfg["model"])

            old_api_key = os.environ.get("OPENAI_API_KEY")
            old_base_url = os.environ.get("OPENAI_BASE_URL")
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_BASE_URL"] = base_url

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.swarm.run(
                        agent=agent,
                        messages=[{"role": "user", "content": task}],
                    ),
                )
                return cfg["role"], response.messages[-1]["content"]
            finally:
                if old_api_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_api_key
                else:
                    os.environ.pop("OPENAI_API_KEY", None)
                if old_base_url is not None:
                    os.environ["OPENAI_BASE_URL"] = old_base_url
                else:
                    os.environ.pop("OPENAI_BASE_URL", None)

        results = await asyncio.gather(
            *[_exec(c) for c in agents_config], return_exceptions=True
        )
        output = {}
        for r in results:
            if isinstance(r, Exception):
                print(f"  [ERROR] {r}")
            else:
                name, content = r
                output[name] = content
        return output

    def select_model(self, prompt: str = "Select model") -> str:
        print(f"\n  {prompt}:")
        print("  --- Ollama (Local) ---")
        for i, m in enumerate(self.ollama_models, 1):
            print(f"    {i}. {m} [Ollama]")
        if self.openrouter_models:
            print("  --- OpenRouter (Cloud) ---")
            offset = len(self.ollama_models)
            for i, m in enumerate(self.openrouter_models, offset + 1):
                free_tag = " [FREE]" if m.get("is_free") else ""
                model_id = m.get("full_id", m)
                print(f"    {i}. {model_id}{free_tag}")
        if self.zai_models:
            print("  --- Z.AI (Cloud) ---")
            offset = len(self.ollama_models) + len(self.openrouter_models)
            for i, m in enumerate(self.zai_models, offset + 1):
                print(f"    {i}. {m['name']} ({m['id']}) [Z.AI]")
        print(f"    0. Use master model ({MASTER_MODEL}) [Z.AI]")
        total = (
            len(self.ollama_models) + len(self.openrouter_models) + len(self.zai_models)
        )
        while True:
            try:
                choice = input("  > ").strip()
                if choice == "0":
                    return MASTER_MODEL
                idx = int(choice) - 1
                if 0 <= idx < len(self.ollama_models):
                    return self.ollama_models[idx]
                idx = idx - len(self.ollama_models)
                if 0 <= idx < len(self.openrouter_models):
                    return self.openrouter_models[idx].get(
                        "full_id", self.openrouter_models[idx]
                    )
                idx = idx - len(self.openrouter_models)
                if 0 <= idx < len(self.zai_models):
                    return self.zai_models[idx]["id"]
                print("  Invalid choice. Try again.")
            except (ValueError, EOFError):
                print("  Invalid input. Try again.")

    def select_role(self) -> tuple:
        print("\n  Select role:")
        for k, (name, desc) in ROLE_PRESETS.items():
            print(f"    {k}. {name} - {desc}")
        print("    6. Custom role")
        while True:
            try:
                choice = input("  > ").strip()
                if choice in ROLE_PRESETS:
                    return ROLE_PRESETS[choice]
                if choice == "6":
                    name = input("  Role name: ").strip() or "custom"
                    desc = input("  Role description: ").strip() or "General purpose."
                    return name, desc
                print("  Invalid choice. Try again.")
            except EOFError:
                return "assistant", "General purpose assistant."


def main():
    system = AgentTeams()

    print("========================================")
    print("       Agent Teams - Interactive")
    print("========================================")
    print(f"  Master: {MASTER_MODEL} (Z.AI)")
    print(f"  Ollama: {len(system.ollama_models)} models")
    print(f"  OpenRouter: {len(system.openrouter_models)} models")
    print(f"  Z.AI: {len(system.zai_models)} models")
    print("  Commands:")
    print("    /task   - Run with sub-agents (select model+role)")
    print("    /multi  - Run multiple sub-agents in parallel")
    print("    /models - List available models")
    print("    /help   - Show commands")
    print("    quit    - Exit")
    print("========================================\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        if user_input == "/models":
            print("\n  --- Ollama (Local) ---")
            for m in system.ollama_models:
                print(f"    - {m}")
            if system.openrouter_models:
                print("\n  --- OpenRouter (Cloud) ---")
                for m in system.openrouter_models:
                    free_tag = " [FREE]" if m.get("is_free") else ""
                    model_id = m.get("full_id", m)
                    print(f"    - {model_id}{free_tag}")
            if system.zai_models:
                print("\n  --- Z.AI (Cloud) ---")
                for m in system.zai_models:
                    print(f"    - {m['name']} ({m['id']})")
            print()
            continue

        if user_input == "/help":
            print("\n  /task   - Single sub-agent task (choose model & role)")
            print("  /multi  - Parallel sub-agents (choose multiple)")
            print("  /models - List all available models")
            print("  /help   - This message")
            print("  quit    - Exit\n")
            continue

        if user_input == "/task":
            task = input("  Task: ").strip()
            if not task:
                continue
            model = system.select_model("Select model for this task")
            role_name, role_desc = system.select_role()
            print(f"\n  Running [{role_name}] with {model}...")
            try:
                result = system.run_single_agent(model, role_name, role_desc, task)
                print(f"\n  [{role_name} ({model})]:")
                print(
                    f"  {result.encode('utf-8', errors='replace').decode('cp932', errors='replace')}"
                )
            except Exception as e:
                print(f"  [ERROR] {e}")
            print()
            continue

        if user_input == "/multi":
            task = input("  Task: ").strip()
            if not task:
                continue
            configs = []
            while True:
                print(f"\n  --- Sub-agent #{len(configs) + 1} ---")
                model = system.select_model(f"Model for agent #{len(configs) + 1}")
                role_name, role_desc = system.select_role()
                configs.append({"model": model, "role": role_name, "desc": role_desc})
                more = input("  Add another agent? (y/n): ").strip().lower()
                if more != "y":
                    break
            print(f"\n  Running {len(configs)} agents in parallel...")
            try:
                results = asyncio.run(system.run_parallel(configs, task))
                for name, content in results.items():
                    print(f"\n  [{name}]:")
                    print(f"  {content}")
            except Exception as e:
                print(f"  [ERROR] {e}")
            print()
            continue

        # Default: Master agent responds
        print()
        try:
            result = system.run_master(user_input)
            print(result)
        except Exception as e:
            print(f"[ERROR] {e}")
        print()


if __name__ == "__main__":
    main()
