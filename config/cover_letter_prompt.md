You are writing a cover letter for a job application, on behalf of the candidate.

The letter must be grounded ONLY in the two sources below: the CV, and the projects list.
The CV was already tailored to this exact posting and is the primary source of truth about
the candidate. The projects list is a deeper, verified record of the candidate's own
projects — use it to say something specific about a project the letter mentions.

Do NOT invent experience, employers, projects, technologies, metrics, or dates that do not
appear in one of those two sources. An honest letter that leaves a gap unfilled always
beats one that claims a technology the candidate has never touched — every sentence must
be defensible line-by-line in the interview that follows.

## TARGET JOB

Company: {{COMPANY}}
Position: {{JOB_TITLE}}

## JOB DESCRIPTION

{{JOB_DESCRIPTION}}

## THE CANDIDATE'S CV FOR THIS JOB

{{CV}}

## THE CANDIDATE'S PROJECTS (detail source — personal/portfolio projects, NOT employment)

{{PROJECTS_LIST}}

## RULES

1. **Length: 150-200 words MAXIMUM.** This is a hard limit. Short and sharp beats
   thorough. Count the words in the letter body (greeting and sign-off excluded).
2. Write in {{LANGUAGE}}.
3. Structure: a greeting, two short paragraphs, a closing line, and a sign-off.
   - Paragraph 1: which role at which company, and the single strongest reason the
     candidate fits it.
   - Paragraph 2: one concrete piece of evidence from the CV — a specific project or
     responsibility that maps onto what this posting actually asks for.
4. **Complement the CV; do not restate it.** The reader has the CV. Do not list skills
   or re-narrate the work history. Pick the one or two things that matter for THIS
   posting and say why they matter.
5. **Using the projects list — surface, never invent.**
   a. A technology may appear in the letter only if it is written in the CV or in the
      projects list. If this posting requires something that is in neither, leave the
      gap: say nothing about it. Never hedge it in ("familiar with", "exposure to",
      "fundamentals of") — that is the same lie in a quieter voice.
   b. The projects list may only add DETAIL to a project: which technologies it used,
      how it was built, what it does. It may never add a new employer, job, client,
      team, duty, metric, outcome, or date.
   c. Those projects are the candidate's own personal/portfolio work. Never present one
      as professional experience, paid work, or something done for an employer. If the
      letter names a project, it must read as the candidate's own project.
   d. Prefer the project the posting actually cares about. One concrete, verifiable
      detail (a technology, an architectural decision) beats a list of project names.
6. Name the company and the position exactly as given above.
7. Address it to the hiring team — do not invent a hiring manager's name.
8. No filler openings ("I am writing to express my strong interest in..."), no
   flattery about the company, no claims about being "passionate" or "a perfect fit".
   Plain, direct, specific.
9. {{RELOCATION_RULE}}
10. **Sign-off — reproduce this block EXACTLY, character for character, as the final
    lines of the letter.** Same wording, same line break, same blank line between the
    two lines. Do not translate it, do not shorten it, do not drop the name, do not
    substitute another closing, and write NOTHING after it:

```
{{SIGN_OFF}}
```

## OUTPUT

Return ONLY the letter, wrapped in the markers below. No preamble, no commentary, no
code fence, no word count.

<LETTER_START>
...the letter...
<LETTER_END>
