# douyin-link-text-extractor

给一个抖音链接，直接提取视频里的**纯文字文案**。

这不是“文案改写器”，也不做 AI 润色。
它只做一件事：**输入一个抖音链接，输出可复制的文字内容**。

## 功能特点

- 支持直接输入抖音分享链接 / 视频链接
- 自动打开页面并抓取真实视频地址
- 自动下载视频并转成文字
- 优先走语音转写（`faster-whisper`）
- 没有有效语音时，自动尝试 OCR / 页面描述兜底
- 支持输出纯文本或 JSON
- 支持保存为 txt 文件

## 为什么这样实现

抖音链接转文字这件事，现成开源项目不少都卡在两类问题：

1. `yt-dlp` 对抖音越来越依赖 fresh cookies
2. 旧版 `iesdouyin` 接口经常返回空 body 或不稳定

所以这个项目换了一个更稳的思路：

1. **用 Playwright 打开抖音页面**
2. **直接从页面真实加载的资源里抓视频地址**
3. **下载视频并调用 `faster-whisper` 做转写**
4. **语音不可用时，再走 OCR / 页面描述兜底**

## 运行环境

- Python 3.10+
- `ffmpeg`
- `tesseract`（用于无语音场景的 OCR 兜底）
- Chrome / Chromium

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y ffmpeg tesseract-ocr tesseract-ocr-chi-sim google-chrome-stable
```

如果你没有系统 Chrome，也可以安装 Playwright 自带浏览器：

```bash
python -m playwright install chromium
```

## 安装

### 方式 1：直接克隆运行

```bash
git clone https://github.com/KeNan-tech620/douyin-link-text-extractor.git
cd douyin-link-text-extractor
python3 -m pip install -r requirements.txt
```

### 方式 2：作为命令行工具安装

```bash
git clone https://github.com/KeNan-tech620/douyin-link-text-extractor.git
cd douyin-link-text-extractor
python3 -m pip install .
```

安装后可以直接使用：

```bash
douyin-link-text 'https://v.douyin.com/xxxx/'
```

## 用法

### 1）直接输出文字

```bash
python3 main.py 'https://v.douyin.com/xxxx/'
```

或者：

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

### 5）切换模型

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

## 输出示例

纯文本：

```text
大家好，今天我要跟大家分享一个特别实用的工具……
```

JSON：

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

## 已知限制

- 抖音网页结构和风控策略会变，未来可能需要跟进修复
- 不是每个链接都 100% 稳定，部分链接可能跳转到精选页、合集页或被风控拦截
- CPU 环境下，长视频转写会比较慢
- OCR 只是兜底方案，纯画面字幕视频的效果不一定稳定
- 当前默认更偏中文场景

## 适合场景

- 快速把单个抖音视频转成文字
- 做视频内容归档
- 接自动化工作流 / 二次处理系统
- 给社群、知识库、搜索系统做文本入库

## 法律与使用说明

请遵守你所在地区的法律法规、平台条款和内容版权要求。
本项目仅用于你有权处理的内容。

## License

MIT
