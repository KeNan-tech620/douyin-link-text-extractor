#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_DEPS = PROJECT_ROOT / ".deps"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

import requests  # type: ignore
from faster_whisper import WhisperModel  # type: ignore
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
from playwright.sync_api import sync_playwright  # type: ignore

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)
CHROME_CANDIDATES = [
    os.getenv("GOOGLE_CHROME_PATH"),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]
VIDEO_PATTERNS = (
    "mime_type=video_mp4",
    "__vid=",
    "/video/tos/",
    ".mp4",
)


@dataclass
class ExtractedVideo:
    input_url: str
    final_page_url: str
    canonical_url: str | None
    aweme_id: str | None
    title: str | None
    description: str | None
    cover_url: str | None
    video_url: str
    subtitle_text: str | None = None


@dataclass
class TranscriptResult:
    text: str
    speech_text: str | None
    ocr_text: str | None
    language: str | None
    duration_seconds: float | None
    elapsed_seconds: float
    metadata: ExtractedVideo


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("请提供抖音链接")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def find_chrome_executable() -> str | None:
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


def choose_video_url(candidates: list[str]) -> str | None:
    clean = []
    for item in candidates:
        if not item:
            continue
        if item.endswith("/uuu_265.mp4"):
            continue
        if any(token in item for token in VIDEO_PATTERNS):
            clean.append(item)
    if not clean:
        return None
    clean = list(dict.fromkeys(clean))
    clean.sort(key=lambda x: ("__vid=" in x, "mime_type=video_mp4" in x, len(x)), reverse=True)
    return clean[0]


def extract_via_browser(url: str, timeout_ms: int = 45000) -> ExtractedVideo:
    chrome_path = find_chrome_executable()
    launch_kwargs: dict[str, Any] = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if chrome_path:
        launch_kwargs["executable_path"] = chrome_path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            locale="zh-CN",
            viewport={"width": 1366, "height": 1600},
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # 继续往下试，很多时候 dom 已经够用了。
            pass

        # 给页面一点时间把播放器资源拉起来。
        page.wait_for_timeout(4000)

        # 某些页面要显式触发一下播放器，真实视频地址才会挂到 currentSrc 上。
        try:
            page.evaluate(
                textwrap.dedent(
                    """
                    () => {
                      const video = document.querySelector('video');
                      if (!video) return false;
                      video.muted = true;
                      video.play?.().catch(() => {});
                      return true;
                    }
                    """
                )
            )
            page.wait_for_timeout(2500)
        except Exception:
            pass

        try:
            page.wait_for_function(
                textwrap.dedent(
                    """
                    () => {
                      const currentSrc = document.querySelector('video')?.currentSrc || '';
                      if (currentSrc.includes('__vid=') || currentSrc.includes('mime_type=video_mp4')) {
                        return true;
                      }
                      const urls = performance.getEntriesByType('resource').map(r => r.name || '');
                      return urls.some(u => (
                        u.includes('mime_type=video_mp4') ||
                        u.includes('__vid=') ||
                        u.includes('/video/tos/') ||
                        /\\.mp4([?#].*)?$/.test(u)
                      ));
                    }
                    """
                ),
                timeout=timeout_ms // 2,
            )
        except PlaywrightTimeoutError:
            # 有些视频不会立刻命中，后面再做一次兜底读取。
            pass

        payload = page.evaluate(
            textwrap.dedent(
                """
                () => {
                  const urls = performance.getEntriesByType('resource').map(r => r.name || '');
                  const candidates = [...new Set(urls.filter(u =>
                    u.includes('mime_type=video_mp4') ||
                    u.includes('__vid=') ||
                    u.includes('/video/tos/') ||
                    /\\.mp4([?#].*)?$/.test(u)
                  ))];

                  const canonical = document.querySelector('link[rel="canonical"]')?.href || null;
                  const title = document.querySelector('meta[property="og:title"]')?.content
                    || document.querySelector('meta[name="lark:url:video_title"]')?.content
                    || document.title
                    || null;
                  const description = document.querySelector('meta[name="description"]')?.content || null;
                  const cover = document.querySelector('meta[property="og:image"]')?.content
                    || document.querySelector('meta[name="lark:url:video_cover_image_url"]')?.content
                    || null;

                  const currentUrl = location.href;
                  const m = (canonical || currentUrl).match(/\\/video\\/(\\d+)/);
                  const awemeId = m ? m[1] : null;
                  const videoEl = document.querySelector('video');
                  const videoCurrentSrc = videoEl?.currentSrc || videoEl?.src || null;

                  const tracks = Array.from(document.querySelectorAll('track'))
                    .map(t => ({src: t.src || null, label: t.label || null, kind: t.kind || null}));

                  return {
                    final_page_url: currentUrl,
                    canonical_url: canonical,
                    title,
                    description,
                    cover_url: cover,
                    video_current_src: videoCurrentSrc,
                    aweme_id: awemeId,
                    candidates,
                    tracks,
                  };
                }
                """
            )
        )
        browser.close()

    raw_candidates: list[str] = []
    if payload.get("video_current_src"):
        raw_candidates.append(payload["video_current_src"])
    raw_candidates.extend(payload.get("candidates", []))

    video_url = choose_video_url(raw_candidates)
    if not video_url:
        raise RuntimeError("没拿到抖音真实视频地址，页面资源里也没抓到 mp4")

    subtitle_text = None
    track_candidates = [t.get("src") for t in payload.get("tracks", []) if t.get("src")]
    if track_candidates:
        subtitle_text = "\n".join(track_candidates)

    return ExtractedVideo(
        input_url=url,
        final_page_url=payload.get("final_page_url") or url,
        canonical_url=payload.get("canonical_url"),
        aweme_id=payload.get("aweme_id"),
        title=payload.get("title"),
        description=payload.get("description"),
        cover_url=payload.get("cover_url"),
        video_url=video_url,
        subtitle_text=subtitle_text,
    )


def extract_via_browser_with_retry(url: str, timeout_ms: int = 45000, attempts: int = 3) -> ExtractedVideo:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return extract_via_browser(url, timeout_ms=timeout_ms)
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def download_video(video_url: str, output_path: Path) -> None:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }
    with requests.get(video_url, headers=headers, stream=True, timeout=120) as response:
        response.raise_for_status()
        with output_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def extract_audio(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(audio_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 提取音频失败: {proc.stderr.strip()}")


def has_audio_stream(video_path: Path) -> bool:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def get_duration_seconds(media_path: Path) -> float | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        return round(float(proc.stdout.strip()), 3)
    except Exception:
        return None


def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    language: str = "zh",
    compute_type: str = "int8",
) -> tuple[str, str | None]:
    cache_dir = PROJECT_ROOT / ".model_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type=compute_type,
        download_root=str(cache_dir),
    )
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 350},
    )
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text, getattr(info, "language", None)


def extract_frames_for_ocr(video_path: Path, frames_dir: Path, duration_seconds: float | None) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    if duration_seconds is None:
        fps = "1"
        max_frames = 12
    elif duration_seconds <= 8:
        fps = "2"
        max_frames = 16
    elif duration_seconds <= 30:
        fps = "1"
        max_frames = 20
    else:
        fps = "1/2"
        max_frames = 24

    pattern = frames_dir / "frame_%03d.jpg"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        "-frames:v",
        str(max_frames),
        str(pattern),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 抽帧失败: {proc.stderr.strip()}")
    return sorted(frames_dir.glob("frame_*.jpg"))


def clean_ocr_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = line.strip("|[](){}<>~`*_—-_=+·•…")
    if not line:
        return ""
    keep = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", line)
    if len(keep) < 2:
        return ""
    if len(set(keep)) <= 1 and len(keep) >= 3:
        return ""
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", line)
    ascii_words = re.findall(r"[A-Za-z]{3,}", line)
    if len(chinese_chars) < 2 and sum(len(w) for w in ascii_words) < 8:
        return ""
    return line


def normalize_dedupe_key(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text).lower()


def is_low_quality_text(text: str) -> bool:
    norm = normalize_dedupe_key(text)
    if len(norm) < 6:
        return True
    unique_chars = len(set(norm))
    if unique_chars <= 1:
        return True
    if unique_chars <= 3 and len(norm) >= 8:
        return True
    top_char_ratio = max(norm.count(ch) for ch in set(norm)) / max(len(norm), 1)
    if top_char_ratio >= 0.45:
        return True
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_word_chars = sum(len(w) for w in re.findall(r"[A-Za-z]{3,}", text))
    if chinese_count < 2 and ascii_word_chars < 10:
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    short_lines = sum(1 for line in lines if len(normalize_dedupe_key(line)) < 4)
    if lines and short_lines / len(lines) > 0.6:
        return True
    if len(lines) <= 2 and chinese_count < 4 and ascii_word_chars < 12:
        return True
    return False


def clean_description_fallback(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"于20\d{2}.*$", "", text)
    text = re.sub(r"，已经收获.*$", "", text)
    text = re.sub(r"\s+-\s+抖音$", "", text)
    return text.strip(" -\n")


def run_tesseract_ocr(image_path: Path) -> str:
    command = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        "chi_sim+eng",
        "--psm",
        "6",
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0 and not proc.stdout:
        return ""
    lines = [clean_ocr_line(line) for line in proc.stdout.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_ocr_text(video_path: Path, duration_seconds: float | None) -> str:
    frames_dir = video_path.parent / "frames"
    frames = extract_frames_for_ocr(video_path, frames_dir, duration_seconds)
    collected: list[str] = []
    seen: set[str] = set()

    for frame in frames:
        raw = run_tesseract_ocr(frame)
        if not raw:
            continue
        for line in raw.splitlines():
            key = normalize_dedupe_key(line)
            if not key or key in seen:
                continue
            # 过滤非常像噪音的内容
            if len(key) < 2:
                continue
            seen.add(key)
            collected.append(line)

    return "\n".join(collected).strip()


def merge_text_sources(speech_text: str, ocr_text: str) -> str:
    speech_text = speech_text.strip()
    ocr_text = ocr_text.strip()

    if speech_text and not ocr_text:
        return speech_text
    if ocr_text and not speech_text:
        return ocr_text
    if not speech_text and not ocr_text:
        return ""

    speech_key = normalize_dedupe_key(speech_text)
    ocr_key = normalize_dedupe_key(ocr_text)
    if speech_key and speech_key in ocr_key:
        return ocr_text
    if ocr_key and ocr_key in speech_key:
        return speech_text
    return f"{speech_text}\n{ocr_text}".strip()


def save_text(path: Path, result: TranscriptResult) -> None:
    body = result.text.strip()
    content = body
    if result.metadata.title:
        content = f"标题：{result.metadata.title}\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


def run(url: str, model: str, language: str, keep_files: bool = False) -> TranscriptResult:
    started = time.time()
    normalized_url = normalize_url(url)
    metadata = extract_via_browser_with_retry(normalized_url)

    work_dir_obj = tempfile.TemporaryDirectory(prefix="douyin-extract-")
    work_dir = Path(work_dir_obj.name)
    video_path = work_dir / "video.mp4"
    audio_path = work_dir / "audio.wav"

    try:
        download_video(metadata.video_url, video_path)
        duration_seconds = get_duration_seconds(video_path)

        speech_text = ""
        detected_language = None
        if has_audio_stream(video_path):
            extract_audio(video_path, audio_path)
            speech_text, detected_language = transcribe_audio(audio_path, model_name=model, language=language)

        ocr_text = ""
        if not speech_text or len(normalize_dedupe_key(speech_text)) < 12:
            ocr_text = extract_ocr_text(video_path, duration_seconds)

        if is_low_quality_text(speech_text):
            speech_text = ""
        if is_low_quality_text(ocr_text):
            ocr_text = ""

        text = merge_text_sources(speech_text, ocr_text)

        if not text:
            text = clean_description_fallback(metadata.description) or clean_description_fallback(metadata.title)

        result = TranscriptResult(
            text=text,
            speech_text=speech_text or None,
            ocr_text=ocr_text or None,
            language=detected_language,
            duration_seconds=duration_seconds,
            elapsed_seconds=round(time.time() - started, 3),
            metadata=metadata,
        )

        if keep_files:
            keep_dir = PROJECT_ROOT / "out"
            keep_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            target_dir = keep_dir / stamp
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video_path, target_dir / "video.mp4")
            shutil.copy2(audio_path, target_dir / "audio.wav")
            (target_dir / "meta.json").write_text(
                json.dumps(asdict(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return result
    finally:
        work_dir_obj.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="输入一个抖音链接，直接提取视频文案")
    parser.add_argument("url", help="抖音分享链接 / 视频链接")
    parser.add_argument("--model", default="base", help="Whisper 模型，默认 base，可改 tiny/base/small/medium/large-v3")
    parser.add_argument("--language", default="zh", help="转写语言，默认 zh")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parser.add_argument("--save", help="把转写结果保存到指定 txt 文件")
    parser.add_argument("--keep-files", action="store_true", help="保留下载的视频/音频和元数据到 out/ 目录")
    parser.add_argument("--verbose", action="store_true", help="输出处理进度到 stderr")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.verbose:
            eprint("[1/3] 解析抖音页面，抓取真实视频地址…")
        result = run(args.url, model=args.model, language=args.language, keep_files=args.keep_files)
        if args.verbose:
            eprint("[2/3] 已下载视频并完成转写…")
            eprint(f"标题: {result.metadata.title or '-'}")
            eprint(f"耗时: {result.elapsed_seconds}s")

        if args.save:
            output_path = Path(args.save).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_text(output_path, result)
            if args.verbose:
                eprint(f"[3/3] 已保存到 {output_path}")

        if args.json:
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        else:
            print(result.text)
        return 0
    except KeyboardInterrupt:
        eprint("已取消")
        return 130
    except Exception as exc:
        eprint(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
