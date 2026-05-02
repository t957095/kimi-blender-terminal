# Installation Guide

I tried to make installation as simple as possible. Here's what you need and how to get running.

## Prerequisites

Before installing the addon, ensure you have:

1. **Blender 3.6+** installed — [Download](https://www.blender.org/download/)
2. **Kimi CLI** installed and authenticated

### Installing Kimi CLI

```bash
# Option 1: via pip
pip install kimi-cli

# Option 2: via uv
uv tool install kimi-cli
```

### Authenticating Kimi CLI

```bash
kimi login
```

Follow the browser prompt to complete OAuth authentication. Your token is stored securely in `~/.kimi/credentials/`.

Verify it works:

```bash
kimi --version
# Expected: kimi version 1.x.x

kimi --output-format stream-json --print --prompt "hello"
# Expected: JSON stream response
```

---

## Method 1: Install from GitHub Source ZIP (Green Code Button)

1. Click the green **Code** button on GitHub and select **Download ZIP**
2. Open Blender
3. Go to **Edit → Preferences → Add-ons**
4. Click **Install from Disk...**
5. Select the downloaded ZIP file
6. Check the box to **Enable** "Kimi Blender Terminal"
7. The MCP Bridge server auto-starts on `localhost:9742`

> The repo includes a root `__init__.py` shim that makes GitHub's source ZIP install correctly in Blender.

---

## Method 2: Install from Pre-built Release ZIP

1. Download `kimi_blender_terminal.zip` from [Releases](../../releases)
2. Install in Blender as described in Method 1

---

## Method 3: Install from Source

```bash
git clone https://github.com/t957095/kimi-blender-terminal.git
cd kimi-blender-terminal
```

Zip the source folder:

```bash
# Windows PowerShell
Compress-Archive -Path kimi_blender_terminal -DestinationPath kimi_blender_terminal.zip

# macOS / Linux
zip -r kimi_blender_terminal.zip kimi_blender_terminal/
```

Then install the ZIP in Blender as described in Method 1.

---

## Method 3: Developer Install (Symlink)

For active development, symlink the source folder into Blender's addons directory:

```bash
# Windows
mklink /J "%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\kimi_blender_terminal" "C:\path\to\kimi-blender-terminal\kimi_blender_terminal"

# macOS
ln -s /path/to/kimi-blender-terminal/kimi_blender_terminal ~/Library/Application\ Support/Blender/4.2/scripts/addons/kimi_blender_terminal

# Linux
ln -s /path/to/kimi-blender-terminal/kimi_blender_terminal ~/.config/blender/4.2/scripts/addons/kimi_blender_terminal
```

Restart Blender and enable the addon.

---

## First-Time Setup

### Addon Preferences

After enabling the addon:

1. Go to **Edit → Preferences → Add-ons → Kimi Blender Terminal**
2. Configure:
   - **Kimi CLI Executable**: Leave blank for auto-detect, or set path to `kimi` / `kimi-cli`
   - **CLI Timeout**: 300 seconds (default)
   - **Max Tool Iterations**: 10 (safety limit)

### Verify Connection

1. Open the 3D View sidebar (press **N**)
2. Click the **Kimi** tab
3. Click the **Test** button (🔌 icon)
4. You should see **● Connected** in the status bar

If you see **● Error**, check:
- Kimi CLI is installed: `kimi --version`
- You're authenticated: `kimi login`
- The executable path is correct in preferences

---

## Updating

### From ZIP

1. Disable the old addon in **Preferences → Add-ons**
2. Install the new ZIP
3. Enable the new version

### From Git

```bash
cd kimi-blender-terminal
git pull origin master
```

Re-zip and reinstall, or restart Blender if using symlink install.

---

## Uninstalling

1. **Edit → Preferences → Add-ons**
2. Find "Kimi Blender Terminal"
3. Click **Remove**
4. Restart Blender
