#!/bin/bash
set -euo pipefail

# Installer for NLSH following XDG Base Directory specification

APP_DIR="$HOME/.local/nlsh"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/nlsh"

# Ask a yes/no question that defaults to No. Succeeds only on an explicit
# "y"/"yes" typed at a terminal; non-interactive input always means No.
confirm_default_no() {
  local reply
  [ -t 0 ] || return 1
  read -rp "$1 [y/N]: " reply || return 1
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

# Remove installs left by the old 'osh' package (renamed to nlsh), which
# put osh.py in ~/osh or ~/.local/osh and linked it as ~/.local/bin/osh.
# A directory with one of those names only counts as a legacy install if
# it contains osh.py, and is removed only after the user confirms.
remove_legacy_osh_installs() {
  local dir
  for dir in "$HOME/osh" "$HOME/.local/osh"; do
    [ -d "$dir" ] || continue
    if [ ! -f "$dir/osh.py" ]; then
      echo "  Leaving $dir alone: it does not look like an old osh installation (no osh.py)."
      continue
    fi
    if [ ! -t 0 ]; then
      echo "  Found old osh installation at $dir; not removing it in a non-interactive run."
      echo "  Remove it yourself if you no longer need it."
      continue
    fi
    if confirm_default_no "  Found old osh installation at $dir. Remove it?"; then
      rm -rf -- "$dir"
    else
      echo "  Keeping $dir."
    fi
  done

  # Only remove the old launcher if it is our symlink to osh.py, not an
  # unrelated program that happens to be called osh.
  local link="$BIN_DIR/osh"
  if [ -L "$link" ] && [[ "$(readlink "$link")" == */osh.py ]]; then
    rm -f -- "$link"
  fi
}

# The installer itself. Kept unindented to keep history readable; it only
# runs when this file is executed, not when it is sourced (e.g. by tests).
main() {
echo "Hello. Installing NLSH..."

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "Warning: $BIN_DIR is not in your PATH."
  echo "After installation, add it to your shell configuration:"
  echo ""
  echo "  # For bash (~/.bashrc or ~/.bash_profile):"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
  echo "  # For zsh (~/.zshrc):"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
fi

echo "- Cleaning up old installation..."
if [ -d "$APP_DIR" ]; then
  read -rp "  Remove existing installation at $APP_DIR? [Y/n]: " confirm_rm
  if [[ ! "$confirm_rm" =~ ^[Nn]$ ]]; then
    rm -rf "$APP_DIR"
  else
    echo "Installation cancelled."
    exit 1
  fi
fi
# Clean up installs from before the osh -> nlsh rename
remove_legacy_osh_installs

# Migrate config from the old 'osh' package name (renamed to nlsh)
if [ -d "$HOME/.config/osh" ] && [ ! -e "$CONFIG_DIR" ]; then
  echo "  Migrating config from ~/.config/osh to $CONFIG_DIR..."
  cp -r "$HOME/.config/osh" "$CONFIG_DIR"
fi

echo "- Creating directories..."
mkdir -p "$APP_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

echo "- Copying application files..."
cp nlsh.py "$APP_DIR/"
cp ask.py "$APP_DIR/"
chmod +x "$APP_DIR/nlsh.py"
chmod +x "$APP_DIR/ask.py"

echo "- Creating executable links in $BIN_DIR..."
ln -sf "$APP_DIR/nlsh.py" "$BIN_DIR/nlsh"
ln -sf "$APP_DIR/ask.py" "$BIN_DIR/ask"
# Also create 'computer' alias for nlsh
ln -sf "$APP_DIR/nlsh.py" "$BIN_DIR/computer"

echo ""
echo "Python Virtual Environment Setup"
echo "================================="
echo ""
echo "Select Python environment for nlsh:"
echo "  1) pyenv virtual environment"
echo "  2) Standard Python venv"
echo "  3) System Python (no virtual environment)"
echo ""
read -rp "Choice [1/2/3]: " venv_choice

PYTHON_CMD="python3"
VENV_CONFIG=""
PYENV_VERSION_NAME=""

case $venv_choice in
  1)
    # pyenv option
    echo ""
    if ! command -v pyenv >/dev/null 2>&1; then
      echo "Error: pyenv not found. Please install pyenv or choose a different option."
      exit 1
    fi

    echo "Available pyenv versions:"
    pyenv versions --bare
    echo ""
    read -rp "Enter pyenv version name (e.g., py312): " pyenv_name

    if ! pyenv versions --bare | grep -q "^${pyenv_name}$"; then
      echo "Warning: pyenv version '$pyenv_name' not found."
      read -rp "Continue anyway? [y/N]: " confirm
      if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        exit 1
      fi
    fi

    PYTHON_CMD="pyenv exec python"
    PYENV_VERSION_NAME="$pyenv_name"
    VENV_CONFIG="pyenv:$pyenv_name"
    echo "Using pyenv environment: $pyenv_name"
    ;;

  2)
    # venv option
    echo ""
    read -rp "Enter path to venv directory (e.g., ~/venvs/nlsh): " venv_path
    venv_path="${venv_path/#\~/$HOME}"  # Expand ~ to full path

    if [ ! -d "$venv_path" ]; then
      echo ""
      read -rp "Virtual environment doesn't exist. Create it? [Y/n]: " create_venv
      if [[ ! "$create_venv" =~ ^[Nn]$ ]]; then
        echo "Creating virtual environment at $venv_path..."
        python3 -m venv "$venv_path"
      else
        echo "Installation cancelled."
        exit 1
      fi
    fi

    PYTHON_CMD="$venv_path/bin/python"
    VENV_CONFIG="venv:$venv_path"
    echo "Using venv at: $venv_path"
    ;;

  3)
    # System Python
    PYTHON_CMD="python3"
    VENV_CONFIG=""
    echo "Using system Python"
    ;;

  *)
    echo "Invalid choice. Please re-run and enter 1, 2, or 3."
    exit 1
    ;;
esac

echo ""
echo "- Installing Python dependencies..."
if [ -n "$PYENV_VERSION_NAME" ]; then
  PYENV_VERSION="$PYENV_VERSION_NAME" pyenv exec python -m pip install -q -r requirements.txt
elif [ "$PYTHON_CMD" = "python3" ]; then
  "$PYTHON_CMD" -m pip install -q --user -r requirements.txt
else
  "$PYTHON_CMD" -m pip install -q -r requirements.txt
fi

# Backend Selection
echo ""
echo "Model Backend Selection"
echo "========================"
echo ""
echo "  1) Ollama (default)"
echo "  2) llama.cpp (llama-server)"
echo ""
read -rp "Select backend [1]: " backend_choice

SELECTED_API="ollama"
SELECTED_MODEL=""
LLAMA_CPP_ENDPOINT=""

if [ "$backend_choice" = "2" ]; then
  SELECTED_API="llama_cpp"

  echo ""
  read -rp "llama.cpp server endpoint URL [http://localhost:38080]: " llama_cpp_endpoint_input
  LLAMA_CPP_ENDPOINT="${llama_cpp_endpoint_input:-http://localhost:38080}"

  MODELS=()
  if command -v curl >/dev/null 2>&1; then
    MODELS_JSON=$(curl -s --max-time 5 "$LLAMA_CPP_ENDPOINT/v1/models" 2>/dev/null || true)
    if [ -n "$MODELS_JSON" ]; then
      mapfile -t MODELS < <(printf '%s' "$MODELS_JSON" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for m in data.get('data', []):
        model_id = m.get('id')
        if model_id:
            print(model_id)
except Exception:
    pass
" 2>/dev/null)
    fi
  fi

  if [ ${#MODELS[@]} -gt 0 ]; then
    echo ""
    echo "Models available from llama-server at $LLAMA_CPP_ENDPOINT:"
    echo ""
    for i in "${!MODELS[@]}"; do
      printf "  %d) %s\n" $((i+1)) "${MODELS[$i]}"
    done
    echo ""
    read -rp "Select model number [or press Enter to type a name]: " model_choice

    if [ -n "$model_choice" ] && \
       [[ "$model_choice" =~ ^[0-9]+$ ]] && \
       [ "$model_choice" -ge 1 ] && \
       [ "$model_choice" -le "${#MODELS[@]}" ]; then
      SELECTED_MODEL="${MODELS[$((model_choice-1))]}"
    fi
  else
    echo ""
    echo "Could not reach $LLAMA_CPP_ENDPOINT to list loaded models."
    echo "(Make sure 'llama-server' is running, or enter the model name manually.)"
  fi

  if [ -z "$SELECTED_MODEL" ]; then
    read -rp "Model name (as loaded by llama-server): " SELECTED_MODEL
  fi
  echo "Selected model: ${SELECTED_MODEL:-<none>}"

else
  # Ollama Model Selection
  echo ""
  echo "Ollama Model Selection"
  echo "======================"
  echo ""

  if command -v ollama >/dev/null 2>&1; then
    echo "Available Ollama models:"
    echo ""

    mapfile -t MODELS < <(ollama list | tail -n +2 | awk '{print $1}' | grep -v '^$')

    if [ ${#MODELS[@]} -eq 0 ]; then
      echo "No models found. Please install a model first using:"
      echo "  ollama pull llama3"
      echo ""
      read -rp "Skip model selection? [Y/n]: " skip_model
      if [[ "$skip_model" =~ ^[Nn]$ ]]; then
        exit 1
      fi
    else
      # Display models with numbers
      for i in "${!MODELS[@]}"; do
        printf "  %d) %s\n" $((i+1)) "${MODELS[$i]}"
      done
      echo ""
      echo "Recommended: llama3:latest (fast, reliable)"
      echo "Note: Avoid reasoning models like deepseek-r1 for shell commands"
      echo ""
      read -rp "Select model number [or press Enter to skip]: " model_choice

      if [ -n "$model_choice" ] && \
         [[ "$model_choice" =~ ^[0-9]+$ ]] && \
         [ "$model_choice" -ge 1 ] && \
         [ "$model_choice" -le "${#MODELS[@]}" ]; then
        SELECTED_MODEL="${MODELS[$((model_choice-1))]}"
        echo "Selected model: $SELECTED_MODEL"
      else
        echo "No model selected, will use default configuration"
      fi
    fi
  else
    echo "Warning: ollama not found. Install it from https://ollama.com"
    echo "Skipping model selection..."
  fi
fi

# Save configuration
echo ""
read -rp "Save configuration to nlsh config? [Y/n]: " save_config
if [[ ! "$save_config" =~ ^[Nn]$ ]]; then
  mkdir -p "$CONFIG_DIR"

  # Pass shell values via environment variables — no shell interpolation inside Python source
  selected_api="$SELECTED_API" selected_model="$SELECTED_MODEL" \
  llama_cpp_endpoint="$LLAMA_CPP_ENDPOINT" \
  venv_config="$VENV_CONFIG" config_dir="$CONFIG_DIR" \
  python3 - <<'PYEOF'
import json, os
from pathlib import Path

config_path = Path(os.environ["config_dir"]) / "config.json"
venv_config  = os.environ.get("venv_config", "")
selected_api = os.environ.get("selected_api", "ollama")
selected_model = os.environ.get("selected_model", "")
llama_cpp_endpoint = os.environ.get("llama_cpp_endpoint", "")

try:
    config = json.loads(config_path.read_text())
except Exception:
    config = {
        "api": "ollama",
        "temperature": 0.3,
        "max_tokens": 2400,
        "safety": True,
        "modify": False,
        "qa_review": True,
        "suggested_command_color": "blue",
        "ollama_endpoint": "http://localhost:11434",
        "ollama_cloud_endpoint": "https://ollama.com",
        "llama_cpp_endpoint": "http://localhost:38080",
        "logging_enabled": True,
        "log_retention_days": 30,
    }

config["api"] = selected_api
if llama_cpp_endpoint:
    config["llama_cpp_endpoint"] = llama_cpp_endpoint
if venv_config:
    config["python_venv"] = venv_config
if selected_model:
    config["model"] = selected_model
elif "model" not in config:
    config["model"] = "llama3:latest"

config_path.write_text(json.dumps(config, indent=2) + "\n")

print(f"Configuration saved to: {config_path}")
print(f"Backend: {selected_api}")
if selected_model:
    print(f"Model: {selected_model}")
if selected_api == "llama_cpp":
    print(f"llama.cpp endpoint: {config['llama_cpp_endpoint']}")
if venv_config:
    print(f"Python environment: {venv_config}")
PYEOF
else
  echo "Configuration not saved. Run 'nlsh --init' to configure later."
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
if [ -f "$CONFIG_DIR/config.json" ]; then
  echo "  1. Review your configuration: $CONFIG_DIR/config.json"
  echo "     (Run 'nlsh --init' to reconfigure)"
else
  echo "  1. Configure nlsh by running: nlsh --init"
fi
echo "  2. If $BIN_DIR is not in your PATH, add it to your shell config"
echo "  3. Restart your shell or run: source ~/.bashrc (or ~/.zshrc)"
echo ""
echo "Usage:"
echo "  nlsh what is my username"
echo "  echo 'your question' | ask"
echo ""
}

if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
  main "$@"
fi
