"""Auto-generate COMMANDS.md from source code."""

import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(REPO_ROOT, "COMMANDS.md")


def extract_mcp_handlers(filepath):
    """Extract @_handler decorated functions with their parameter usage."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    handlers = []
    # Find @_handler blocks
    pattern = r'@_handler\("([^"]+)"\)\s*\n(def _[a-zA-Z_0-9]+\([^)]*\):(?:\n(?:    .*\n?)*)?)'
    for m in re.finditer(pattern, source):
        name = m.group(1)
        func_block = m.group(2)

        # Extract params.get("...") and params.get('...')
        params_found = set()
        for pm in re.finditer(r'''params\.get\(["']([^"']+)["']''', func_block):
            params_found.add(pm.group(1))
        for pm in re.finditer(r'''params\[["']([^"']+)["']\]''', func_block):
            params_found.add(pm.group(1))

        # Extract docstring
        doc = ""
        doc_match = re.search(r'"""(.*?)"""', func_block, re.DOTALL)
        if doc_match:
            doc = doc_match.group(1).strip().split("\n")[0]

        handlers.append((name, sorted(params_found), doc))
    return handlers


def extract_tools(filepath):
    """Extract @tool_registry.tool decorated functions with schemas."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    tools = []
    # Match decorator + function definition
    pattern = r'@tool_registry\.tool\((.*?)\)\s*\ndef ([a-zA-Z_0-9]+)\((.*?)\):\s*\n'
    for m in re.finditer(pattern, source, re.DOTALL):
        decorator = m.group(1).strip()
        func_name = m.group(2)
        sig = m.group(3).strip()

        # Extract name
        name_match = re.search(r'name\s*=\s*"([^"]+)"', decorator)
        tool_name = name_match.group(1) if name_match else func_name

        # Extract description
        desc_match = re.search(r'description\s*=\s*"([^"]+)"', decorator)
        description = desc_match.group(1) if desc_match else ""

        # Extract params schema (JSON-like dict)
        params_schema = ""
        params_match = re.search(r'params\s*=\s*(\{.*?\})(?:,|\))', decorator, re.DOTALL)
        if params_match:
            params_schema = params_match.group(1).strip()

        tools.append((tool_name, func_name, sig, description, params_schema))
    return tools


def extract_module_functions(filepath):
    """Extract public functions with docstrings from a module."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    funcs = []
    # Parse with ast for reliability
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return funcs

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            name = node.name
            if name.startswith("__") and name.endswith("__"):
                continue
            # Get signature
            args = []
            defaults_start = len(node.args.args) - len(node.args.defaults)
            for i, arg in enumerate(node.args.args):
                arg_name = arg.arg
                if i >= defaults_start:
                    default = node.args.defaults[i - defaults_start]
                    if isinstance(default, ast.Constant):
                        args.append(f"{arg_name}={default.value!r}")
                    else:
                        args.append(f"{arg_name}=...")
                else:
                    args.append(arg_name)
            # kwonly args
            kw_defaults_start = len(node.args.kwonlyargs) - len(node.args.kw_defaults)
            for i, arg in enumerate(node.args.kwonlyargs):
                arg_name = arg.arg
                if i >= kw_defaults_start:
                    default = node.args.kw_defaults[i - kw_defaults_start]
                    if isinstance(default, ast.Constant):
                        args.append(f"{arg_name}={default.value!r}")
                    else:
                        args.append(f"{arg_name}=...")
                else:
                    args.append(f"{arg_name}")

            sig = ", ".join(args)

            # Get docstring
            doc = ast.get_docstring(node) or ""
            doc = doc.strip().split("\n")[0] if doc else ""

            funcs.append((name, sig, doc))
    return funcs


def extract_executor_namespace(filepath):
    """Extract functions that are injected into the executor namespace."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    funcs = []
    # Find all def _... functions that look like helpers
    pattern = r'^[ ]*def (_[a-zA-Z_0-9]+)\(([^)]*)\):\s*\n(?:[ ]*"""(.*?)"""|[ ]*\'\'\'(.*?)\'\'\')?'
    for m in re.finditer(pattern, source, re.MULTILINE | re.DOTALL):
        name = m.group(1)
        sig = m.group(2).strip()
        doc = (m.group(3) or m.group(4) or "").strip()
        doc = doc.split("\n")[0] if doc else ""
        # Skip private internals
        if name in ("__init__", "_lock"):
            continue
        funcs.append((name, sig, doc))
    return funcs


def extract_color_constants(filepath):
    """Extract COLOR_* or color constant definitions."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    colors = []
    # Look for patterns like RED = (1.0, 0.0, 0.0)
    for m in re.finditer(r'^([A-Z]+)\s*=\s*\(([^)]+)\)', source, re.MULTILINE):
        name = m.group(1)
        val = m.group(2)
        if any(c in name for c in ["RED", "GREEN", "BLUE", "YELLOW", "ORANGE", "WHITE", "BLACK", "GREY", "SILVER", "GOLD", "CYAN", "MAGENTA", "PURPLE", "PINK", "BROWN"]):
            colors.append((name, val))
    return colors


def main():
    lines = []
    lines.append("# Kimi Blender Terminal — Command Reference\n")
    lines.append("Auto-generated from source code.\n")
    lines.append("---\n")

    # === MCP BRIDGE ===
    lines.append("## MCP Bridge Commands\n")
    lines.append("JSON-over-TCP on `localhost:9742`. Send: `{'type': '<cmd>', 'params': {...}}`\n")

    mcp_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "mcp_bridge.py")
    handlers = extract_mcp_handlers(mcp_path)
    for name, params, doc in sorted(handlers, key=lambda x: x[0]):
        lines.append(f"### `{name}`")
        if doc:
            lines.append(f"*{doc}*")
        if params:
            lines.append(f"- **Params:** {', '.join(f'`{p}`' for p in params)}")
        lines.append("")

    # === TOOL REGISTRY ===
    lines.append("---\n")
    lines.append("## Tool Registry (XML `<tool_call>`)\n")
    lines.append("Invoke via XML blocks: `<tool_call><name>tool</name><arguments>{...}</arguments></tool_call>`\n")

    bt_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "blender_tools.py")
    tools = extract_tools(bt_path)
    for tool_name, func_name, sig, desc, schema in sorted(tools, key=lambda x: x[0]):
        lines.append(f"### `{tool_name}`")
        if desc:
            lines.append(f"*{desc}*")
        if sig:
            lines.append(f"- **Signature:** `{func_name}({sig})`")
        if schema:
            # Format schema nicely
            lines.append(f"- **Schema:** `{schema.replace(chr(10), ' ')}`")
        lines.append("")

    # === EXECUTOR HELPERS ===
    lines.append("---\n")
    lines.append("## Executor Helpers (Available in `execute_code` namespace)\n")

    exec_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "executor.py")
    helpers = extract_executor_namespace(exec_path)
    for name, sig, doc in sorted(helpers, key=lambda x: x[0]):
        lines.append(f"### `{name}({sig})`")
        if doc:
            lines.append(f"*{doc}*")
        lines.append("")

    # === WEB EXPORTER ===
    lines.append("---\n")
    lines.append("## Web Exporter\n")
    web_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "web_exporter.py")
    web_funcs = extract_module_functions(web_path)
    for name, sig, doc in sorted(web_funcs, key=lambda x: x[0]):
        if name.startswith("_"):
            continue
        lines.append(f"### `{name}({sig})`")
        if doc:
            lines.append(f"*{doc}*")
        lines.append("")

    # === DATA VIZ ===
    lines.append("---\n")
    lines.append("## Data Visualization\n")
    viz_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "data_viz.py")
    viz_funcs = extract_module_functions(viz_path)
    for name, sig, doc in sorted(viz_funcs, key=lambda x: x[0]):
        if name.startswith("_"):
            continue
        lines.append(f"### `{name}({sig})`")
        if doc:
            lines.append(f"*{doc}*")
        lines.append("")

    # === BLENDERKIT ===
    lines.append("---\n")
    lines.append("## BlenderKit Integration\n")
    bk_path = os.path.join(REPO_ROOT, "kimi_blender_terminal", "blenderkit_integration.py")
    bk_funcs = extract_module_functions(bk_path)
    for name, sig, doc in sorted(bk_funcs, key=lambda x: x[0]):
        if name.startswith("_"):
            continue
        lines.append(f"### `{name}({sig})`")
        if doc:
            lines.append(f"*{doc}*")
        lines.append("")

    # === CLI BRIDGE ===
    lines.append("---\n")
    lines.append("## CLI Bridge Arguments\n")
    lines.append("```bash")
    lines.append('python cli_bridge.py "create a red cube" --turns 10 --screenshots ./shots')
    lines.append("```\n")
    lines.append("| Argument | Default | Description |")
    lines.append("|---|---|---|")
    lines.append("| `prompt` | — | Text prompt to send to Kimi |")
    lines.append("| `--prompt-file, -f` | — | Read prompt from a text file |")
    lines.append("| `--host` | `localhost` | Blender MCP Bridge host |")
    lines.append("| `--port` | `9742` | Blender MCP Bridge port |")
    lines.append("| `--turns` | `5` | Max autonomous turns |")
    lines.append("| `--timeout` | `300` | Kimi CLI timeout (seconds) |")
    lines.append("| `--screenshots, -s` | — | Directory to save viewport screenshots |")
    lines.append("| `--save-blend` | `False` | Auto-save `.blend` every 2 turns |")
    lines.append("| `--verbose, -v` | `False` | Show thinking and full code |")
    lines.append("| `--blend` | — | Open a `.blend` file before executing |")
    lines.append("| `--list-tools` | — | List available tools and exit |")
    lines.append("")

    # === COLOR CONSTANTS ===
    lines.append("---\n")
    lines.append("## Color Constants (Executor Namespace)\n")
    colors = [
        ("RED", "(1.0, 0.0, 0.0)"), ("GREEN", "(0.0, 1.0, 0.0)"), ("BLUE", "(0.0, 0.0, 1.0)"),
        ("YELLOW", "(1.0, 1.0, 0.0)"), ("ORANGE", "(1.0, 0.5, 0.0)"), ("WHITE", "(1.0, 1.0, 1.0)"),
        ("BLACK", "(0.0, 0.0, 0.0)"), ("GREY", "(0.5, 0.5, 0.5)"), ("SILVER", "(0.8, 0.8, 0.8)"),
        ("GOLD", "(1.0, 0.84, 0.0)"), ("CYAN", "(0.0, 1.0, 1.0)"), ("MAGENTA", "(1.0, 0.0, 1.0)"),
        ("PURPLE", "(0.5, 0.0, 0.5)"), ("PINK", "(1.0, 0.75, 0.8)"), ("BROWN", "(0.6, 0.3, 0.1)"),
    ]
    lines.append("| Name | RGB Value |")
    lines.append("|---|---|")
    for name, val in colors:
        lines.append(f"| `{name}` | `{val}` |")
    lines.append("")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
