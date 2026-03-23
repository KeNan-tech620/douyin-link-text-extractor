#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/5] 安装系统依赖..."
sudo apt update
sudo apt install -y \
  python3 \
  python3-pip \
  python3-venv \
  ffmpeg \
  tesseract-ocr \
  tesseract-ocr-chi-sim

echo "[2/5] 创建虚拟环境..."
python3 -m venv .venv
source .venv/bin/activate

echo "[3/5] 安装 Python 依赖..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/5] 安装 Playwright Chromium..."
python -m playwright install chromium

echo "[5/5] 检查核心依赖..."
python --version
ffmpeg -version | head -n 1
tesseract --list-langs | sed -n '1,20p'

echo
echo "安装完成。"
echo "运行示例："
echo "  cd $ROOT"
echo "  ./run.sh 'https://v.douyin.com/xxxx/' --verbose"
