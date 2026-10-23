"""Claude Code agent'larını başsız (headless, `claude -p`) çalıştıran küçük başlatıcı.

Projenin model çağıran her yolu buradan geçer:
  * poller döngüsü ve cv_uret.command → /cv-uret
  * regenerate.py                      → /cv-yenile
  * panelin "Mektup" butonu ve CLI      → /mektup

Neden subprocess ve neden bu ortam değişkenleri:
  * ANTHROPIC_API_KEY child ortamdan SİLİNİR. .env bu anahtarı (panel özeti için) yüklüyor;
    `claude -p` ortamda anahtar görürse girişli aboneliği değil API'yi faturalar. Bu da
    agent sistemine geçişin asıl amacını (maliyet) boşa çıkarır.
  * CLAUDE_EFFORT SİLİNİR: Claude Code kendi effort'unu bu adla ihraç ediyor, model/effort
    seçimini --model / --effort bayraklarıyla açıkça veriyoruz.
  * CLAUDECODE SİLİNİR: bir Claude Code oturumunun içinden (ör. geliştirirken) başlatılan
    iç içe `claude`, bu değişkeni görünce çalışmayı reddediyor.

Bu modül sadece stdlib + config + reporting import eder. summary_api de bunu import
ettiği için Playwright/pipeline zincirine asla bağlanmamalı (bkz. CLAUDE.md).
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .config import PROJECT_ROOT, STATE_DIR, settings
from .reporting import record_failure

logger = logging.getLogger(__name__)

# /cv-uret aynı anda iki kez çalışmasın: poller ile cv_uret.command aynı satırı birlikte
# görürse ikisi de aynı satıra CV üretip numarayı iki kez harcar.
CV_LOCK_FILE = STATE_DIR / "agent_cv.lock"

# Child ortamdan çıkarılan değişkenler (gerekçesi modül açıklamasında).
_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "CLAUDE_EFFORT", "CLAUDECODE")

# Başsız oturumda agent'ların hiç kullanamayacağı araçlar. Agent'lar dış dünyaya sadece
# cv-tools MCP sunucusu üzerinden dokunur; LinkedIn'i yalnızca o sunucudaki misafir
# görünümlü scraper okur (kullanıcının oturumu asla otomasyona bağlanmaz).
_DISALLOWED_TOOLS = "Bash,WebFetch,WebSearch"

# claude CLI'nin kabul ettiği effort değerleri. "none" ya da boş → bayrak hiç verilmez.
_EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}

# Süre sınırları (saniye). Bir CV medium effort'ta ~2-5 dk sürüyor.
CV_BATCH_TIMEOUT = 60 * 60
REGEN_TIMEOUT = 60 * 60
COVER_LETTER_TIMEOUT = 6 * 60


class AgentBusy(RuntimeError):
    """Başka bir /cv-uret çalışması kilidi tutuyor."""


@dataclass
class AgentResult:
    ok: bool
    text: str
    cost_usd: float | None = None
    duration_s: float = 0.0
    raw: dict = field(default_factory=dict)


def claude_bin() -> str:
    """claude CLI'nin yolu: CLAUDE_BIN → PATH → ~/.local/bin/claude."""
    if settings.claude_bin:
        return settings.claude_bin
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    if fallback.exists():
        return str(fallback)
    raise FileNotFoundError(
        "claude CLI bulunamadı. Claude Code'u kurun ya da .env'e CLAUDE_BIN=<yol> ekleyin."
    )


def _child_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}


def run_claude(prompt: str, *, model: str, effort: str, timeout: int) -> AgentResult:
    """`claude -p <prompt>` çalıştırır ve JSON sonucunu döndürür.

    İzinler `.claude/settings.json`'dan gelir; `dontAsk` modunda izin listesinde olmayan
    her şey sormadan reddedilir, böylece başsız oturum asla bir onay ekranında takılmaz.
    """
    cmd = [
        claude_bin(),
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--model",
        model,
        "--disallowedTools",
        _DISALLOWED_TOOLS,
    ]
    if effort in _EFFORT_LEVELS:
        cmd += ["--effort", effort]

    logger.info("Agent starting: %r (model=%s effort=%s)", prompt, model, effort or "-")
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - started
        record_failure("agent_run", error=f"{prompt!r} {timeout}s içinde bitmedi")
        return AgentResult(ok=False, text="", duration_s=duration)
    duration = time.monotonic() - started

    raw: dict = {}
    try:
        raw = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("Agent output is not JSON: %s", (proc.stdout or "")[:500])

    text = str(raw.get("result", "") or "")
    cost = raw.get("total_cost_usd")
    ok = proc.returncode == 0 and not raw.get("is_error", False)
    logger.info(
        "Agent finished: %r ok=%s duration=%.0fs turns=%s cost_usd=%s",
        prompt, ok, duration, raw.get("num_turns"), cost,
    )
    if text:
        logger.info("Agent report:\n%s", text)
    if not ok:
        detail = text or (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        record_failure("agent_run", error=f"{prompt!r}: {detail}")
    return AgentResult(ok=ok, text=text, cost_usd=cost, duration_s=duration, raw=raw)


@contextmanager
def _cv_lock():
    """/cv-uret için süreçler arası kilit. Meşgulse beklemez, AgentBusy fırlatır."""
    CV_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CV_LOCK_FILE.open("a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AgentBusy("Başka bir CV üretimi zaten çalışıyor.") from exc
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def run_cv_batch(
    only_row: int | None = None, limit: int | None = None, allow_staged: bool = False
) -> AgentResult:
    """B == "Üretilecek" satırları için /cv-uret'i çalıştırır."""
    args = []
    if only_row is not None:
        args.append(f"--row {only_row}")
    if limit is not None:
        args.append(f"--limit {limit}")
    if allow_staged:
        args.append("--allow-staged")
    prompt = " ".join(["/cv-uret", *args])
    with _cv_lock():
        return run_claude(
            prompt, model=settings.cv_model, effort=settings.cv_effort, timeout=CV_BATCH_TIMEOUT
        )


def run_regenerate(start: int, end: int, instruction: str = "") -> AgentResult:
    """Kaydedilmiş ilan metinlerinden [start, end] aralığını /cv-yenile ile yeniden üretir."""
    prompt = f"/cv-yenile {start} {end}"
    instruction = " ".join((instruction or "").split())
    if instruction:
        prompt += f" {instruction}"
    with _cv_lock():
        return run_claude(
            prompt, model=settings.cv_model, effort=settings.cv_effort, timeout=REGEN_TIMEOUT
        )


def run_cover_letter(cv_no: int, lang: str, force: bool = False) -> AgentResult:
    """Tek bir mektup için /mektup çalıştırır. Kilit yok: mektup CV numarası harcamaz."""
    prompt = f"/mektup {cv_no} {lang}" + (" --force" if force else "")
    return run_claude(
        prompt, model=settings.cover_letter_model, effort="low", timeout=COVER_LETTER_TIMEOUT
    )
