# douyin-link-text-extractor

输入一个抖音链接，直接提取视频里的**纯文字文案**。

它的目标很简单：
- 不做文案改写
- 不做润色扩写
- 不依赖第三方大模型 API Key
- 只把抖音视频尽量稳定地转成可复制的文字

## 功能

- 支持抖音分享链接 / 视频链接
- 自动打开抖音页面并抓取真实视频地址
- 自动下载视频并转成文字
- 优先走 `faster-whisper` 语音转写
- 没有有效语音时，自动尝试 OCR / 页面描述兜底
- 支持输出纯文本或 JSON
- 支持保存为 txt 文件

## 为什么这么做

这个需求看起来简单，但实际做起来很容易卡在两类问题：

1. `yt-dlp` 对抖音越来越依赖 fresh cookies
2. 旧版 `iesdouyin` 接口经常返回空 body 或不稳定

所以这个项目用的是更稳一点的方案：

1. 用 **Playwright** 打开抖音页面
2. 从页面真实加载的资源里抓视频地址
3. 下载视频并调用 **faster-whisper** 转写
4. 语音不可用时，再走 **OCR / 页面描述** 兜底

## 本地部署需要什么

部署到本地，核心只需要这些：

- Python 3.10+
- `ffmpeg`
- `tesseract-ocr`
- `tesseract-ocr-chi-sim`
- Chrome / Chromium（或 Playwright 自带 Chromium）

### 可选环境变量

#### `GOOGLE_CHROME_PATH`

如果你的 Chrome / Chromium 不在默认路径，可以手动指定：

```bash
export GOOGLE_CHROME_PATH=/path/to/chrome
```

> 不配也可以。项目会优先找系统浏览器；如果没有，再使用 Playwright 安装的 Chromium。

---

## Ubuntu / Debian 一键部署

仓库自带了一个本地部署脚本：

```bash
git clone https://github.com/KeNan-tech620/douyin-link-text-extractor.git
cd douyin-link-text-extractor
bash scripts/setup_ubuntu.sh
```

这个脚本会自动做这些事：

- 安装系统依赖
- 创建 `.venv`
- 安装 Python 依赖
- 安装 Playwright Chromium
- 做基础环境检查

部署完成后，直接运行：

```bash
./run.sh 'https://v.douyin.com/xxxx/' --verbose
```

---

## 手动安装

如果你不想跑脚本，也可以手动装。

### 1）安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg tesseract-ocr tesseract-ocr-chi-sim
```

### 2）克隆项目

```bash
git clone https://github.com/KeNan-tech620/douyin-link-text-extractor.git
cd douyin-link-text-extractor
```

### 3）创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4）安装 Playwright 浏览器

```bash
python -m playwright install chromium
```

### 5）运行

```bash
./run.sh 'https://v.douyin.com/xxxx/'
```

> `run.sh` 会优先使用项目里的 `.venv/bin/python`，所以部署后直接跑就行，不一定每次都要手动激活虚拟环境。

---

## 用法

### 1）直接输出文字

```bash
./run.sh 'https://v.douyin.com/xxxx/'
```

### 2）保存成 txt

```bash
./run.sh 'https://v.douyin.com/xxxx/' --save ./out/result.txt
```

### 3）输出 JSON

```bash
./run.sh 'https://v.douyin.com/xxxx/' --json
```

### 4）看处理进度

```bash
./run.sh 'https://v.douyin.com/xxxx/' --verbose
```

### 5）切换 Whisper 模型

```bash
./run.sh 'https://v.douyin.com/xxxx/' --model small
```

可选模型：

- `tiny`
- `base`
- `small`
- `medium`
- `large-v3`

默认模型是 `base`。

---

## 输出示例

### 纯文本

```text
大家好，今天我要跟大家分享一个特别实用的工具……
```

### JSON

```json
{
  "text": "转写后的正文",
  "speech_text": "Whisper 语音识别结果",
  "ocr_text": "OCR 兜底结果",
  "language": "zh",
  "duration_seconds": 164.188,
  "elapsed_seconds": 27.206,
  "metadata": {
    "input_url": "https://v.douyin.com/xxxx/",
    "final_page_url": "https://www.douyin.com/video/xxxx",
    "aweme_id": "xxxx"
  }
}
```

---

## 适合场景

- 快速把单个抖音视频转成文字
- 做视频内容归档
- 接自动化工作流 / 二次处理系统
- 给社群、知识库、搜索系统做文本入库

## 已知限制

- 抖音网页结构和风控策略会变，未来可能需要跟进修复
- 不是每个链接都 100% 稳定，部分链接可能跳转到精选页、合集页或被风控拦截
- CPU 环境下，长视频转写会比较慢
- OCR 只是兜底方案，纯画面字幕视频的效果不一定稳定
- 当前默认更偏中文场景

## 排查建议

如果本地跑不起来，优先检查这几项：

```bash
python3 --version
ffmpeg -version
ffprobe -version
tesseract --list-langs
./run.sh --help
```

如果浏览器相关报错，补装：

```bash
python -m playwright install chromium
```

如果系统浏览器不在默认位置，手动指定：

```bash
export GOOGLE_CHROME_PATH=/path/to/chrome
```

## 法律与使用说明

请遵守你所在地区的法律法规、平台条款和内容版权要求。
本项目仅用于你有权处理的内容。

## License

MIT
