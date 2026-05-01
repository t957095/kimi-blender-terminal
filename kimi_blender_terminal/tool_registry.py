"""
ToolRegistry — MCP-style tool definitions with JSON schemas.

Tools are registered with a decorator and exposed as:
    {
        "name": str,
        "description": str,
        "parameters": dict,  # JSON Schema
        "func": callable,
    }

The conversation agent instructs the assistant to emit:
    <tool_call>
    <name>tool_name</name>
    <arguments>{"key":"value"}</arguments>
    </tool_call>
"""

import json
import inspect
import re

REGISTRY = {}


def tool(name: str = None, description: str = None, params: dict = None):
    """Decorator to register a tool."""
    def decorator(func):
        tname = name or func.__name__
        tdesc = description or (func.__doc__ or "").strip().split("\n")[0]
        # Auto-build params from function signature if not provided
        tparams = params
        if tparams is None:
            sig = inspect.signature(func)
            props = {}
            required = []
            for pname, p in sig.parameters.items():
                if pname in ("ctx", "context"):
                    continue
                ptype = "string"
                pdefault = p.default
                if p.annotation == int or p.default is not inspect.Parameter.empty and isinstance(p.default, int):
                    ptype = "integer"
                elif p.annotation == float or p.default is not inspect.Parameter.empty and isinstance(p.default, float):
                    ptype = "number"
                elif p.annotation == bool or p.default is not inspect.Parameter.empty and isinstance(p.default, bool):
                    ptype = "boolean"
                elif p.annotation == list or p.default is not inspect.Parameter.empty and isinstance(p.default, list):
                    ptype = "array"
                elif p.annotation == dict or p.default is not inspect.Parameter.empty and isinstance(p.default, dict):
                    ptype = "object"
                prop = {"type": ptype}
                if p.default is not inspect.Parameter.empty:
                    prop["default"] = p.default
                else:
                    required.append(pname)
                props[pname] = prop
            tparams = {"type": "object", "properties": props}
            if required:
                tparams["required"] = required
        REGISTRY[tname] = {
            "name": tname,
            "description": tdesc,
            "parameters": tparams,
            "func": func,
        }
        return func
    return decorator


def get_tool(name: str):
    return REGISTRY.get(name)


def list_tools() -> list:
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in REGISTRY.values()
    ]


def build_system_tool_prompt() -> str:
    """Build the system prompt section that describes available tools."""
    lines = [
        "You have access to the following tools. Use them by emitting XML blocks exactly like this:",
        "",
        "<tool_call>",
        "<name>tool_name</name>",
        "<arguments>{\"key\":\"value\"}</arguments>",
        "</tool_call>",
        "",
        "You may emit multiple <tool_call> blocks in a single response. They will be executed in order.",
        "If no tool is needed, respond normally without XML tags.",
        "Always prefer using tools over writing raw Python code unless the user explicitly asks for code.",
        "",
        "Available tools:",
        "",
    ]
    for t in list_tools():
        lines.append(f"- {t['name']}: {t['description']}")
        lines.append(f"  Parameters schema: {json.dumps(t['parameters'])}")
        lines.append("")
    return "\n".join(lines)


def parse_tool_calls(text: str) -> list:
    """Parse <tool_call> ... </tool_call> blocks from model response."""
    calls = []
    pattern = r"<tool_call>\s*<name>(.*?)</name>\s*<arguments>(.*?)</arguments>\s*</tool_call>"
    for m in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
        name = m.group(1).strip()
        args_raw = m.group(2).strip()
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            # Try to fix common issues like single quotes, trailing commas
            try:
                fixed = args_raw.replace("'", '"').replace(",}", "}").replace(",]", "]")
                args = json.loads(fixed)
            except Exception:
                args = {"raw": args_raw}
        calls.append({"name": name, "arguments": args})
    return calls


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a registered tool by name with JSON arguments."""
    t = REGISTRY.get(name)
    if not t:
        return {"status": "error", "message": f"Tool '{name}' not found. Available: {', '.join(REGISTRY.keys())}"}
    func = t["func"]
    params_schema = t.get("parameters", {})
    required = params_schema.get("required", [])
    props = params_schema.get("properties", {})

    # Validate required args
    missing = [r for r in required if r not in arguments]
    if missing:
        return {"status": "error", "message": f"Missing required params for '{name}': {missing}"}

    # Filter to only known params
    known = {k: v for k, v in arguments.items() if k in props}

    try:
        result = func(**known)
        if isinstance(result, dict) and "status" in result:
            return result
        return {"status": "success", "result": result}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": tb}


def get_tools_prompt() -> str:
    """Build a concise tool description for the system prompt."""
    lines = [
        "You have access to structured TOOLS. Use them for reliability.",
        "Format: <tool_call><name>tool_name</name><arguments>{\"key\":\"value\"}</arguments></tool_call>",
        "You may use multiple <tool_call> blocks in one response. They execute in order.",
        "For operations NOT covered by tools, use ```python code blocks.",
        "",
        "Available tools:",
    ]
    for t in list_tools():
        lines.append(f"  {t['name']}: {t['description']}")
        req = t['parameters'].get('required', [])
        if req:
            lines.append(f"    Required: {', '.join(req)}")
    return "\n".join(lines)


