"""CV generation via the Anthropic API.

Builds the ATS-optimization prompt from config assets and returns both the full
model response (Turkish analysis + tables) and the clean optimized CV markdown.
"""
from __future__ import annotations

import logging
import re

import anthropic

from .config import (
    ATS_PROMPT_FILE,
    ATS_REVIEW_PROMPT_FILE,
    CV_BASE_FILE,
    PROJECTS_LIST_FILE,
    settings,
)

logger = logging.getLogger(__name__)

_MATCH_RATE_RE = re.compile(r"<MATCH_RATE>\s*(\d+(?:\.\d+)?)\s*</MATCH_RATE>")

# The job's top two priority programming languages, e.g. "Python, Java" (primary first).
_LANGUAGES_RE = re.compile(r"<LANGUAGES>\s*(.*?)\s*</LANGUAGES>", re.DOTALL)

# Output cap. Only a ceiling (you're billed for tokens actually generated), so keep it
# generous to avoid truncating the CV mid-output. The full analysis + CV alone can run
# ~7-8k tokens, so 8k was too tight.
MAX_TOKENS = 16000
# When adaptive thinking is on, the reply ALSO contains thinking tokens (counted against
# max_tokens), which can be large. Use sonnet 4.6's streamable ceiling so medium/high
# effort never truncates before emitting the CV. Streaming makes a high cap safe.
MAX_TOKENS_THINKING = 64000

# Reasoning effort levels accepted by output_config.effort on Sonnet 5 / Sonnet 4.6 /
# Opus 4.x. "none" => no extended thinking (thinking explicitly disabled; a plain, fast,
# cheapest request). Sonnet 5 also accepts "xhigh", but it is costly — not enabled here.
_EFFORT_LEVELS = {"low", "medium", "high", "max"}


BASE_RELOCATION_SENTENCE = "Open to relocation and on-site or hybrid opportunities."

# Column G (Uzaktan) values that mean the job needs the candidate on location. The
# sheet's dropdown spells it "Hybrit"; the rest are tolerated spellings. Shared with
# cover_letter.py so the two relocation rules can't drift apart.
ONSITE_WORK_MODES = {"on-site", "onsite", "on site", "hybrit", "hybrid"}


def _relocation_instruction(work_mode: str, city: str) -> str:
    """Build the SUMMARY closing-sentence rule from the row's work mode and city."""
    wm = work_mode.strip().lower()
    city = city.strip()
    if wm == "remote":
        return (
            "The job is REMOTE. In the SUMMARY, REMOVE the final sentence "
            f'"{BASE_RELOCATION_SENTENCE}" completely and do not replace it with anything.'
        )
    if wm in ONSITE_WORK_MODES:
        new_sentence = f"Open to relocation ({city}) and on-site or hybrid opportunities."
        return (
            f"The job is {work_mode.strip()} (on-site/hybrid). The SUMMARY's final sentence "
            f'MUST read EXACTLY: "{new_sentence}"'
        )
    return (
        "Keep the SUMMARY's final sentence exactly as in the original CV: "
        f'"{BASE_RELOCATION_SENTENCE}"'
    )


def _extra_instruction_block(instruction: str) -> str:
    """Render the per-run user override that regenerate.py's --instruction supplies.

    Empty when no instruction is given, so the placeholder disappears cleanly. When set,
    it is a HIGH-PRIORITY directive for THIS run (which project to drop/feature, emphasis,
    ordering...), but it deliberately does NOT license fabrication: the honesty contract
    still holds, so any project/skill it names must be real (in the PROJECTS LIST or the
    CURRENT CV). This keeps the swap defensible in an interview.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return ""
    return (
        "---\n\n"
        "# ⚠️ PER-RUN USER OVERRIDE (HIGHEST PRIORITY)\n\n"
        "For THIS regeneration only, apply the user's instruction below. It OVERRIDES "
        "conflicting selection/layout defaults above (e.g. which projects to include, "
        "their order, what to emphasize).\n\n"
        "It does NOT override the honesty contract: every project, skill or detail you "
        "add or keep MUST be real — present in the PROJECTS LIST or the CURRENT CV. If "
        "the instruction asks for something none of the sources support, follow it only "
        "as far as the real facts allow and state the gap in your Turkish analysis; never "
        "fabricate to satisfy it.\n\n"
        f"USER INSTRUCTION:\n{instruction}\n"
    )


def _build_prompt(
    job_description: str, work_mode: str, city: str, instruction: str = ""
) -> str:
    template = ATS_PROMPT_FILE.read_text(encoding="utf-8")
    cv_base = CV_BASE_FILE.read_text(encoding="utf-8")
    projects = PROJECTS_LIST_FILE.read_text(encoding="utf-8")
    return (
        template.replace("{{PROJECTS_LIST}}", projects)
        .replace("{{CV_BASE}}", cv_base)
        .replace("{{SUMMARY_RELOCATION_RULE}}", _relocation_instruction(work_mode, city))
        .replace("{{JOB_DESCRIPTION}}", job_description.strip())
        .replace("{{EXTRA_INSTRUCTION}}", _extra_instruction_block(instruction))
    )


def _strip_fence(cv: str) -> str:
    """Strip an accidental wrapping ``` code fence the model may have added."""
    cv = cv.strip()
    if cv.startswith("```"):
        cv = re.sub(r"^```[a-zA-Z]*\n", "", cv)
        cv = re.sub(r"\n```$", "", cv).strip()
    return cv


def _extract_cv(full_response: str) -> str:
    """Extract the optimized CV from between <CV_START>..<CV_END>.

    The model occasionally emits a STRAY <CV_START> earlier (e.g. inside its analysis),
    leaving several start markers. Taking the first one then captures analysis junk. So
    we take the LAST block that actually begins with a section header ('### ' — i.e. the
    real CV), falling back to the last block if none match.
    """
    starts = [m.end() for m in re.finditer("<CV_START>", full_response)]
    if not starts:
        raise ValueError(
            "Could not find <CV_START>...<CV_END> markers in the model response."
        )
    blocks = []
    for s in starts:
        e = full_response.find("<CV_END>", s)
        blocks.append(full_response[s : e if e != -1 else len(full_response)])
    for body in reversed(blocks):
        cv = _strip_fence(body)
        if cv.startswith("### "):
            return cv
    return _strip_fence(blocks[-1])


def _extract_match_rate(full_response: str) -> float | None:
    match = _MATCH_RATE_RE.search(full_response)
    if not match:
        logger.warning("No <MATCH_RATE> marker found in the model response.")
        return None
    return float(match.group(1))


def extract_languages(full_response: str) -> str:
    """Return the job's top two priority programming languages, e.g. "Python, Java".

    Parsed from the <LANGUAGES>...</LANGUAGES> marker the model emits (primary language
    first, second alternative next). Returns "" when the marker is missing or empty (the
    posting named no language) — the caller then leaves the sheet cell blank.
    """
    match = _LANGUAGES_RE.search(full_response)
    if not match:
        logger.warning("No <LANGUAGES> marker found in the model response.")
        return ""
    # Collapse any stray inner whitespace/newlines to a clean "A, B".
    return " ".join(match.group(1).split())


def _call_model(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": settings.claude_model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    effort = settings.claude_effort
    if effort in _EFFORT_LEVELS:
        # Adaptive thinking + effort is the current API (budget_tokens is rejected on
        # Sonnet 5 / Sonnet 4.6 / Opus 4.x). Effort controls how much the model thinks;
        # cost scales with it, so "low" is the cheapest thinking-on setting.
        kwargs["max_tokens"] = MAX_TOKENS_THINKING
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}
    else:
        # effort == "none": thinking OFF, and we set it EXPLICITLY. On Sonnet 5 an
        # omitted `thinking` runs adaptive thinking by DEFAULT (unlike Sonnet 4.6, where
        # omitting meant thinking-off), which would silently add billed thinking tokens.
        # Disabling keeps this the cheap, plain single-pass request across both models.
        kwargs["thinking"] = {"type": "disabled"}
    # Stream so large (high-effort) requests aren't blocked by the 10-min non-stream limit.
    with client.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    u = getattr(message, "usage", None)
    if u is not None:
        # Output tokens include extended-thinking tokens, which dominate cost at higher effort.
        logger.info(
            "Token usage: input=%s output=%s (model=%s effort=%s)",
            getattr(u, "input_tokens", "?"),
            getattr(u, "output_tokens", "?"),
            settings.claude_model,
            settings.claude_effort,
        )
    # Only collect answer text; skip "thinking" blocks.
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )


def generate(
    job_description: str, work_mode: str = "", city: str = "", instruction: str = ""
) -> tuple[str, str, float | None]:
    """Return (full_response, optimized_cv_markdown, match_rate).

    `instruction` is an optional per-run user override (regenerate.py --instruction),
    woven into the prompt as a high-priority directive that still obeys the honesty
    contract (see `_extra_instruction_block`).
    """
    prompt = _build_prompt(job_description, work_mode, city, instruction)
    logger.info("Requesting CV from %s ...", settings.claude_model)
    full = _call_model(prompt)
    return full, _extract_cv(full), _extract_match_rate(full)


def review(
    job_description: str,
    cv_draft: str,
    work_mode: str = "",
    city: str = "",
    instruction: str = "",
) -> tuple[str, str, float | None]:
    """Second expert pass: verify the draft CV against the job and FIX problems.

    Returns (full_review_response, corrected_cv_markdown, final_match_rate). `instruction`
    is threaded through so an enabled review pass honors the same per-run override and
    doesn't "correct" the requested change back out.
    """
    template = ATS_REVIEW_PROMPT_FILE.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{PROJECTS_LIST}}", PROJECTS_LIST_FILE.read_text(encoding="utf-8"))
        .replace("{{CV_BASE}}", CV_BASE_FILE.read_text(encoding="utf-8"))
        .replace("{{SUMMARY_RELOCATION_RULE}}", _relocation_instruction(work_mode, city))
        .replace("{{JOB_DESCRIPTION}}", job_description.strip())
        .replace("{{CV_DRAFT}}", cv_draft.strip())
        .replace("{{EXTRA_INSTRUCTION}}", _extra_instruction_block(instruction))
    )
    logger.info("Reviewing CV (expert QA pass) with %s ...", settings.claude_model)
    full = _call_model(prompt)
    return full, _extract_cv(full), _extract_match_rate(full)
