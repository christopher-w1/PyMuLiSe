#!/bin/bash

VENV_DIR="./venv"
ENV_VARS_FILE=".env_vars.sh"
START_SCRIPT="start_env.sh"

# 1. Create virtual environment if not exists
if [ ! -d "$VENV_DIR" ]; then
    echo "🟢 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "✅ Virtual environment already exists."
fi

# 2. Install requirements if available
if [ -f "requirements.txt" ]; then
    echo "📦 Installing packages from requirements.txt..."
    "$VENV_DIR/bin/pip" install -r requirements.txt
else
    echo "⚠️ No requirements.txt found – skipping installation."
fi

# 3. Create .env_vars.sh if not exists
if [ ! -f "$ENV_VARS_FILE" ]; then
    echo "🔧 Setting up environment variables (only once)..."
    read -p "Enter your LASTFM_API_KEY: " lastfm
    read -p "Enter the absolute path to your MUSIC_DIR: " music
    read -p "Enter your REST_API_PORT (e.g. 8080): " port

    echo "export LASTFM_API_KEY=\"$lastfm\"" > "$ENV_VARS_FILE"
    echo "export MUSIC_DIR=\"$music\"" >> "$ENV_VARS_FILE"
    echo "export REST_API_PORT=\"$port\"" >> "$ENV_VARS_FILE"

    echo "✅ Saved environment variables to $ENV_VARS_FILE"
else
    echo "🔒 Environment variable file already exists: $ENV_VARS_FILE"
fi

# 4. Create start_env.sh
cat <<EOF > "$START_SCRIPT"
#!/bin/bash
source "$ENV_VARS_FILE"
source "$VENV_DIR/bin/activate"
echo "✅ Virtual environment activated with environment variables."
EOF

chmod +x "$START_SCRIPT"
echo "🚀 Created launch script: $START_SCRIPT"

# 5. Final hint
echo
echo "💡 To activate everything later, run:"
echo "   source $START_SCRIPT"
