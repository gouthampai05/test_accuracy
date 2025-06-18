#!/bin/bash

set -e

# Constants
PYTHON_VERSION=3.11.9
PYTHON_MAJOR_MINOR=3.11
VENV_NAME="env"
RUN_OUTPUT_DIR="output"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

function show_usage() {
    echo -e "${YELLOW}🚀 Usage:"
    echo -e "  chmod +x ./manage.sh         ${NC}# Make script executable"
    echo -e "  sudo ./manage.sh setup       ${NC}# Install dependencies & create venv"
    echo -e "  sudo ./manage.sh run <dir>   ${NC}# Run OCR detection on directory"
    echo -e "  sudo ./manage.sh dashboard   ${NC}# Launch interactive dashboard"
    exit 1
}

# Ensure running with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}🔐 Please run this script with sudo:${NC}"
    echo "    sudo $0 $*"
    exit 1
fi

# Always check OS
if ! grep -qiE 'debian|ubuntu' /etc/os-release; then
    echo -e "${RED}❌ Unsupported OS. Only Debian-based systems supported.${NC}"
    exit 1
fi

# Ensure an argument is passed
if [ $# -lt 1 ]; then
    echo -e "${RED}❌ Missing argument.${NC}"
    show_usage
fi

function setup_env() {
    echo -e "${GREEN}🔍 Detected Debian-based OS. Proceeding...${NC}"
    echo -e "${YELLOW}🔄 Updating package list...${NC}"
    apt-get update -y

    DEPS=(
        wget build-essential libssl-dev zlib1g-dev
        libbz2-dev libreadline-dev libsqlite3-dev curl
        libncursesw5-dev xz-utils tk-dev libxml2-dev
        libxmlsec1-dev libffi-dev liblzma-dev git
    )

    echo -e "${GREEN}📦 Checking system dependencies...${NC}"
    for pkg in "${DEPS[@]}"; do
        dpkg -s "$pkg" &> /dev/null || {
            echo -e "➡️  Installing: $pkg"
            apt-get install -y "$pkg"
        }
    done

    echo -e "${GREEN}🐍 Checking Python version...${NC}"
    if command -v python3.11 &> /dev/null; then
        INSTALLED_VERSION=$(python3.11 --version | awk '{print $2}')
        if [ "$INSTALLED_VERSION" == "$PYTHON_VERSION" ]; then
            echo -e "${GREEN}✅ Python $PYTHON_VERSION already installed.${NC}"
        else
            echo -e "${RED}⚠️ Version mismatch: $INSTALLED_VERSION found.${NC}"
            install_pyenv_prompt
        fi
    else
        echo -e "${YELLOW}🔍 Python 3.11 not found.${NC}"
        install_pyenv_prompt
    fi

    cd "$(dirname "$0")"

    # Handle venv overwrite
    if [ -d "$VENV_NAME" ]; then
        echo -e "${YELLOW}⚠️ Virtual environment '$VENV_NAME' already exists.${NC}"
        read -p "🗑️ Do you want to delete and recreate it? [y/N]: " response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}🧹 Removing old virtual environment...${NC}"
            rm -rf "$VENV_NAME"
        else
            echo -e "${RED}❌ Aborting setup. Please delete or rename the existing venv first.${NC}"
            exit 1
        fi
    fi

    echo -e "${YELLOW}🌱 Creating virtual environment: $VENV_NAME${NC}"
    python3.11 -m venv "$VENV_NAME"

    echo -e "${YELLOW}📦 Installing Python packages from requirements.txt...${NC}"
    source "$VENV_NAME/bin/activate"

    if [ ! -f requirements.txt ]; then
        echo -e "${RED}❌ Missing requirements.txt.${NC}"
        exit 1
    fi

    pip install --upgrade pip
    pip install -r requirements.txt

    echo -e "${GREEN}✅ Setup complete! Environment is ready.${NC}"
}

function install_pyenv_prompt() {
    read -p "⚠️ Install Python $PYTHON_VERSION via pyenv? [y/N]: " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        if ! command -v pyenv &> /dev/null; then
            echo -e "${YELLOW}📥 Installing pyenv...${NC}"
            curl https://pyenv.run | bash
            export PATH="$HOME/.pyenv/bin:$PATH"
            eval "$(pyenv init -)"
            eval "$(pyenv virtualenv-init -)"
        fi
        echo -e "${YELLOW}📦 Installing Python $PYTHON_VERSION...${NC}"
        pyenv install $PYTHON_VERSION
        pyenv global $PYTHON_VERSION
    else
        echo -e "${RED}❌ Cannot continue without correct Python version.${NC}"
        exit 1
    fi
}

function run_ocr() {
    if [ ! -d "$VENV_NAME" ]; then
        echo -e "${RED}❌ Virtual environment not found. Please run 'sudo ./manage.sh setup' first.${NC}"
        exit 1
    fi

    if [ -z "$2" ]; then
        echo -e "${RED}❌ Please provide a directory path for OCR input.${NC}"
        exit 1
    fi

    echo -e "${GREEN}📂 Running OCR on directory: $2${NC}"
    source "$VENV_NAME/bin/activate"
    mkdir -p "$RUN_OUTPUT_DIR"
    python3 app/main.py "$2" "$RUN_OUTPUT_DIR"
    echo -e "${GREEN}✅ OCR completed. Output saved to ${RUN_OUTPUT_DIR}/.${NC}"
}

function run_dashboard() {
    if [ ! -d "$RUN_OUTPUT_DIR" ]; then
        echo -e "${RED}❌ No OCR output found. Run 'sudo ./manage.sh run <dir>' first.${NC}"
        exit 1
    fi

    echo -e "${GREEN}📊 Launching dashboard...${NC}"
    source "$VENV_NAME/bin/activate"
    python3 app/dashboard.py "$RUN_OUTPUT_DIR"
}

# ------------------------- MAIN SWITCH ------------------------- #
case "$1" in
    setup)
        setup_env
        ;;
    run)
        run_ocr "$@"
        ;;
    dashboard)
        run_dashboard
        ;;
    *)
        echo -e "${RED}❌ Invalid argument: $1${NC}"
        show_usage
        ;;
esac
