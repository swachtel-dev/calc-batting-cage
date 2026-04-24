#!/usr/bin/env python3
"""
Build problems.json for the Calc II Batting Cage from problem_bank_ch*.md.

Run from any cwd:
    python3 build_problems.py

Reads:
    ../problem_bank_ch7.md, ch8.md, ch9.md, ch10.md
    (Ch 11-12 intentionally skipped: Calc III material, out of Calc II scope.)

Writes:
    ./problems.json
    A JSON object keyed by Paul's section id (e.g. "7.1"), each entry containing
    { id, title, chapter, chapterNum, notesUrl, problems: [...] }.
    Each problem is { prompt, problem, answer, solution }.

Design:
    - MD files are the source of truth for batting-cage content: they're cleanly
      section-tagged (unlike the main question_bank.csv, where 372 rows lost
      their pauls_section tag during canonicalization).
    - If later we want to port specific Tier C/D fixes from the CSV, do it by
      hand in this script's PROBLEM_OVERRIDES dict (keyed by (section, problem_num)).
    - The HTML loads problems.json at runtime; updating problems does NOT require
      editing index.html.

Usage:
    python3 build_problems.py
    python3 build_problems.py --verify   # also print per-section counts

To deploy:
    cp problems.json index.html to the git repo, commit, push.
    GitHub Pages auto-deploys within ~60 seconds.
"""
import json
import os
import re
import sys
import glob

DRAFTS_DIR = os.path.dirname(os.path.abspath(__file__))
CALC_II_ROOT = os.path.abspath(os.path.join(DRAFTS_DIR, '..'))
MD_FILES = sorted(glob.glob(os.path.join(CALC_II_ROOT, 'problem_bank_ch*.md')))
# Skip Ch 11-12 — these are Calc III material (vectors / 3D space) and out of
# Calc II scope. If a future course needs them, drop this filter.
EXCLUDE = {'problem_bank_ch11_12.md'}
MD_FILES = [f for f in MD_FILES if os.path.basename(f) not in EXCLUDE]

BANK_CSV = os.path.join(CALC_II_ROOT, 'question_bank.csv')

OUT_PATH = os.path.join(DRAFTS_DIR, 'problems.json')

# Map Paul's section id → course unit. Drives UI grouping so students see
# "Unit 3: Integration by Parts" rather than "Ch 7" (which confusingly reads
# as a unit number).
SECTION_TO_UNIT = {
    '7.1': 3, '7.2': 3,
    '7.3': 4, '7.4': 4, '7.5': 4, '7.6': 4,
    '7.7': 5, '7.8': 5, '7.9': 5, '7.10': 5,
    '8.1': 6, '8.2': 6, '8.3': 6, '8.4': 6, '8.5': 6,
    '9.1': 8, '9.2': 8, '9.3': 8, '9.4': 8, '9.5': 8,
    '9.6': 9, '9.7': 9, '9.8': 9, '9.9': 9, '9.10': 9, '9.11': 9,
    '10.1': 10, '10.2': 10, '10.3': 10, '10.4': 10, '10.5': 10,
    '10.6': 11, '10.7': 11, '10.8': 11, '10.9': 11, '10.10': 11, '10.11': 11, '10.12': 11,
    '10.13': 12, '10.14': 12, '10.15': 12, '10.16': 12, '10.17': 12, '10.18': 12,
    # U2 sections (Calc I Ch 6 content, synthesized below from question_bank.csv)
    '6.1': 2, '6.2': 2, '6.3': 2, '6.4': 2,
}

# Titles for the course units, shown as group headers in the UI.
UNIT_TITLES = {
    2:  'Volumes of Revolution and Work',
    3:  'Integration by Parts and Trig Integrals',
    4:  'Trig Substitution and Partial Fractions',
    5:  'Integration Strategy and Improper Integrals',
    6:  'Applications of Integration',
    8:  'Parametric Equations',
    9:  'Polar Coordinates',
    10: 'Sequences and Series Foundations',
    11: 'Convergence Tests',
    12: 'Power Series and Taylor Series',
}

# Map Paul section ID (from MD "### Section ID: XYZ" line) to notes URL.
# Paul uses the same slug in his URL: /Classes/CalcII/{SectionID}.aspx
# Calc I sections use the Calc I URL root. Detected by section title prefix
# ("Calc I —" or specific names we know are Calc I).
CALC_I_SECTION_IDS = {
    # Add as we discover them in the MD files. Currently none — all ch 7-10 are Calc II.
}

# Chapter metadata for display (driven by the MD chapter heading).
CHAPTER_NAMES = {
    7:  'Integration Techniques',
    8:  'Applications of Integrals',
    9:  'Parametric Equations & Polar Coordinates',
    10: 'Sequences & Series',
}

def paul_url_for(section_id, section_num):
    """Build the Paul's notes URL for a given section_id slug."""
    # Detect if this is Calc I (currently all our MD content is Calc II)
    if section_id in CALC_I_SECTION_IDS:
        return f'https://tutorial.math.lamar.edu/Classes/CalcI/{section_id}.aspx'
    return f'https://tutorial.math.lamar.edu/Classes/CalcII/{section_id}.aspx'


def collapse_display_math(text):
    """Collapse internal whitespace in every \\[ ... \\] and \\( ... \\) block
    to a single space.

    The batting cage's solution renderer replaces raw \\n with <br> BEFORE
    handing off to KaTeX auto-render, which breaks multi-line display-math
    blocks because KaTeX can't span HTML tags. Single-line blocks render fine.
    """
    def _collapse(m):
        inner = m.group(1)
        inner = re.sub(r'\s+', ' ', inner).strip()
        return m.group(0)[:2] + ' ' + inner + ' ' + m.group(0)[-2:]
    # Display: \[ ... \]
    text = re.sub(r'\\\[(.*?)\\\]', _collapse, text, flags=re.DOTALL)
    # Inline: \( ... \)  — collapse just in case
    text = re.sub(r'\\\((.*?)\\\)', _collapse, text, flags=re.DOTALL)
    return text


def normalize_problem_or_answer(text):
    """Return text formatted for the app's renderMathInElement path.

    The app renders problem + answer via KaTeX auto-render, which scans for
    \\(...\\) (inline) and \\[...\\] (display) delimiters. Our MD source has
    three patterns:
      1. Pure math wrapped: '\\( \\int x e^{3x} \\, dx \\)'   → already OK
      2. Pure math bare:    '\\int x e^{3x} \\, dx'           → wrap in \\[...\\]
      3. Prose + inline:    'Find the Maclaurin series for \\( f(x) = ... \\).'
                                                              → already OK (inline math rendered, prose as text)

    We rewrite bare math into a display block so KaTeX auto-render picks it up.
    """
    text = text.strip()
    # Drop legacy $...$ / $$...$$ wrappers in favor of \(...\) / \[...\]
    # (single expression only; don't touch mid-sentence $ if any)
    m = re.match(r'^\$\$(.*)\$\$$', text, re.DOTALL)
    if m:
        return '\\[ ' + re.sub(r'\s+', ' ', m.group(1)).strip() + ' \\]'
    m = re.match(r'^\$(.*)\$$', text, re.DOTALL)
    if m:
        return '\\( ' + m.group(1).strip() + ' \\)'
    # If the text contains no \( or \[ delimiters, decide whether it's bare
    # math (wrap in \[...\]) or plain prose (leave as-is).
    if '\\(' not in text and '\\[' not in text:
        # Count runs of 4+ alphabetic characters. Two or more such runs means
        # the content is prose (e.g., "rectangular plate submerged"), not math.
        word_runs = re.findall(r'[A-Za-z]{4,}', text)
        has_backslash_command = bool(re.search(r'\\[a-zA-Z]+', text))
        if has_backslash_command or len(word_runs) < 2:
            # Pure math or a math-like short expression. Wrap as display.
            return '\\[ ' + re.sub(r'\s+', ' ', text).strip() + ' \\]'
        # Prose. Leave as-is so KaTeX auto-render treats it as plain text.
        return text
    # Already has delimiters (either pure-math wrapped or prose+inline math);
    # leave as-is.
    return text


def parse_md_file(path):
    """Parse one problem_bank_chN.md. Returns list of section dicts."""
    with open(path) as f:
        content = f.read()

    # Chapter number from filename (ch7.md → 7)
    m = re.search(r'ch(\d+)', os.path.basename(path))
    ch_num = int(m.group(1)) if m else 0

    sections_out = []
    # Split on ## Section headings
    section_blocks = re.split(r'\n## Section ', content)
    for block in section_blocks[1:]:
        # First line: "7.1: Integration by Parts"
        hm = re.match(r'([\d.]+):\s*([^\n]+)', block)
        if not hm:
            continue
        sec_num = hm.group(1)
        sec_title = hm.group(2).strip()

        # Section ID line: "### Section ID: IntegrationByParts"
        idm = re.search(r'### Section ID:\s*(\S+)', block)
        section_id = idm.group(1) if idm else ''

        # Parse problems. Each block is:
        #   **Problem N.** <problem text>
        #   **Solution.**
        #   <solution body>
        #   **Answer:** <answer>
        # Separated by ---
        prob_blocks = re.split(r'\n\*\*Problem\s+\d+\.\*\*\s*', block)
        problems = []
        for pb in prob_blocks[1:]:
            # Split at **Solution.**
            parts = re.split(r'\n\*\*Solution\.\*\*\s*\n', pb, maxsplit=1)
            problem_text = parts[0].strip()
            if len(parts) < 2:
                # Malformed — skip
                continue
            rest = parts[1]
            # Split at **Answer:**
            sol_ans = re.split(r'\n\*\*Answer:\*\*\s*', rest, maxsplit=1)
            solution_text = sol_ans[0].strip()
            answer_text = sol_ans[1].strip() if len(sol_ans) > 1 else ''
            # Strip trailing --- and trailing newlines
            answer_text = re.sub(r'\n---.*$', '', answer_text, flags=re.DOTALL).strip()
            # Normalize problem and answer so the app's renderMathInElement
            # path handles every pattern (bare math, wrapped math, prose+math).
            problem_clean = normalize_problem_or_answer(problem_text)
            answer_clean = normalize_problem_or_answer(answer_text)
            # Solution: collapse multi-line display math to single line so the
            # app's \n→<br> replacement doesn't break KaTeX auto-render.
            solution_clean = collapse_display_math(solution_text)
            problems.append({
                'prompt': default_prompt_for_section(sec_num, sec_title),
                'problem': problem_clean,
                'answer': answer_clean,
                'solution': solution_clean,
            })

        unit = SECTION_TO_UNIT.get(sec_num)
        sections_out.append({
            'id': sec_num,
            'title': sec_title,
            'sectionId': section_id,
            'chapter': CHAPTER_NAMES.get(ch_num, f'Chapter {ch_num}'),
            'chapterNum': ch_num,
            'unit': unit,
            'unitTitle': UNIT_TITLES.get(unit, '') if unit else '',
            'notesUrl': paul_url_for(section_id, sec_num) if section_id else '',
            'problems': problems,
        })
    return sections_out


def build_calc1_sections_from_csv():
    """Synthesize U2-coverage sections from question_bank.csv Calc I rows.

    The MD files only cover Paul's Ch 7-10, leaving U1-U2 with no batting-cage
    content. The CSV has 85 Calc I rows (area, volumes, work, avg fcn value)
    with solutions populated — these became the batting cage's natural U2 pack.
    """
    import csv
    if not os.path.exists(BANK_CSV):
        return []
    rows = list(csv.DictReader(open(BANK_CSV)))
    calc1 = [r for r in rows if r.get('pauls_section','').startswith('Calc I')]
    # Normalize section names (bank has both "Calc I - Area Between Curves" and
    # "Calc I - AreaBetweenCurves"; merge).
    def normalize_calc1(name):
        n = name.replace('Calc I - ', '').replace(' ', '').lower()
        if 'area' in n and 'between' in n: return ('6.1', 'Area Between Curves')
        if 'volumewithrings' in n or 'volumes(rings)' in n: return ('6.2', 'Volumes of Revolution: Disks and Washers')
        if 'volumewithcylinder' in n or 'volumes(cylinders)' in n: return ('6.3', 'Volumes of Revolution: Shells')
        if 'morevolume' in n: return ('6.3', 'Volumes of Revolution: Shells')
        if 'avgfcn' in n or 'averagefunction' in n: return (None, None)  # not in U2 scope
        if 'work' in n: return ('6.4', 'Work')
        return (None, None)

    from collections import defaultdict
    buckets = defaultdict(list)  # (sec_id, sec_title) → [problem dicts]
    for r in calc1:
        sec_id, sec_title = normalize_calc1(r['pauls_section'])
        if not sec_id:
            continue
        # Strip $...$ delimiters on question/answer to feed normalize_problem_or_answer
        problem_text = r.get('question_text','').strip()
        answer_text = r.get('answer','').strip()
        solution_text = r.get('solution','').strip()
        # Use the same normalizers as the MD path for consistency
        problem_clean = normalize_problem_or_answer(problem_text)
        answer_clean = normalize_problem_or_answer(answer_text)
        solution_clean = collapse_display_math(solution_text)
        # Convert $...$ inside solution prose to \( \) for KaTeX auto-render.
        # The CSV uses $ delimiters; the batting cage's auto-render config
        # expects \( \) and \[ \] only.
        solution_clean = convert_dollar_delimiters(solution_clean)
        problem_clean = convert_dollar_delimiters(problem_clean)
        answer_clean = convert_dollar_delimiters(answer_clean)
        prompt = default_prompt_for_u2_section(sec_id)
        buckets[(sec_id, sec_title)].append({
            'prompt': prompt,
            'problem': problem_clean,
            'answer': answer_clean,
            'solution': solution_clean,
        })

    # Emit sorted by section id
    out = []
    for (sec_id, sec_title), probs in sorted(buckets.items()):
        unit = SECTION_TO_UNIT.get(sec_id)
        out.append({
            'id': sec_id,
            'title': sec_title,
            'sectionId': '',
            'chapter': 'Applications of the Integral (Calc I review)',
            'chapterNum': 6,
            'unit': unit,
            'unitTitle': UNIT_TITLES.get(unit, ''),
            'notesUrl': calc1_notes_url(sec_id),
            'problems': probs,
        })
    return out


def default_prompt_for_u2_section(sec_id):
    return {
        '6.1': 'Find the area of the region bounded by the given curves.',
        '6.2': 'Find the volume of the solid of revolution using the disk or washer method.',
        '6.3': 'Find the volume of the solid of revolution using the method of cylindrical shells.',
        '6.4': 'Solve the following work problem.',
    }.get(sec_id, 'Solve the following problem.')


def calc1_notes_url(sec_id):
    return {
        '6.1': 'https://tutorial.math.lamar.edu/Classes/CalcI/AreaBetweenCurves.aspx',
        '6.2': 'https://tutorial.math.lamar.edu/Classes/CalcI/VolumeWithRings.aspx',
        '6.3': 'https://tutorial.math.lamar.edu/Classes/CalcI/VolumeWithCylinder.aspx',
        '6.4': 'https://tutorial.math.lamar.edu/Classes/CalcI/Work.aspx',
    }.get(sec_id, '')


def convert_dollar_delimiters(text):
    """Convert $$...$$ to \\[...\\] and $...$ to \\(...\\). Bank uses $-delimiters.

    Conservative: only convert balanced pairs on lines/segments that look like math.
    """
    # Display math: $$...$$ → \[ ... \]
    text = re.sub(r'\$\$([^$]+?)\$\$', lambda m: '\\[ ' + m.group(1).strip() + ' \\]', text, flags=re.DOTALL)
    # Inline: $...$ → \( ... \)
    text = re.sub(r'\$([^$\n]+?)\$', lambda m: '\\( ' + m.group(1).strip() + ' \\)', text)
    return text


def default_prompt_for_section(section_num, section_title):
    """Choose a sensible default prompt based on the section topic.
    The MD source doesn't include prompts per-problem, so we use the section
    context to give a generic directive.
    """
    sec = section_num
    t = section_title.lower()
    if sec.startswith('7.'):
        if 'integration by parts' in t:
            return 'Evaluate the following integral using integration by parts.'
        if 'trig' in t and 'sub' not in t:
            return 'Evaluate the following integral.'
        if 'trig sub' in t or 'substitution' in t:
            return 'Evaluate the following integral using a trigonometric substitution.'
        if 'partial fraction' in t:
            return 'Evaluate the following integral using partial fraction decomposition.'
        if 'improper' in t:
            return 'Evaluate the following improper integral, or determine that it diverges.'
        if 'comparison' in t:
            return 'Determine whether the following improper integral converges or diverges.'
        if 'approximating' in t:
            return 'Approximate the following integral using the specified rule.'
        if 'strategy' in t:
            return 'Identify the appropriate integration technique and evaluate the integral.'
        return 'Evaluate the following integral.'
    if sec.startswith('8.'):
        if 'arc length' in t: return 'Compute the arc length.'
        if 'surface area' in t: return 'Compute the surface area of revolution.'
        if 'center of mass' in t: return 'Find the centroid of the described region.'
        if 'hydrostatic' in t: return 'Compute the hydrostatic force on the described plate.'
        if 'probability' in t: return 'Answer the following probability question.'
        return 'Solve the following problem.'
    if sec.startswith('9.'):
        if 'parametric' in t:
            if 'tangent' in t: return 'Find the requested tangent information for the parametric curve.'
            if 'area' in t: return 'Compute the area.'
            if 'arc length' in t: return 'Compute the arc length of the parametric curve.'
            if 'surface area' in t: return 'Compute the surface area for the parametric curve.'
            return 'Work with the following parametric curve.'
        if 'polar' in t:
            if 'tangent' in t: return 'Find the tangent to the polar curve.'
            if 'area' in t: return 'Compute the area.'
            if 'arc length' in t: return 'Compute the arc length of the polar curve.'
            if 'surface area' in t: return 'Compute the surface area for the polar curve.'
            return 'Work with the following polar curve.'
        return 'Solve the following problem.'
    if sec.startswith('10.'):
        if 'sequence' in t: return 'Determine whether the sequence converges. If it does, find its limit.'
        if 'basics' in t or 'convergence/divergence' in t: return 'Determine whether the series converges or diverges.'
        if 'special' in t: return 'Determine convergence and, if possible, find the sum.'
        if 'integral test' in t: return 'Use the Integral Test to determine convergence.'
        if 'comparison' in t: return 'Use a Comparison Test to determine convergence.'
        if 'alternating' in t: return 'Use the Alternating Series Test.'
        if 'absolute' in t: return 'Classify the series as absolutely convergent, conditionally convergent, or divergent.'
        if 'ratio' in t: return 'Apply the Ratio Test.'
        if 'root' in t: return 'Apply the Root Test.'
        if 'strategy' in t: return 'Determine convergence. Name the test you used.'
        if 'estimating' in t: return 'Estimate the value of the series.'
        if 'power series' in t and 'function' not in t: return 'Find the radius and interval of convergence.'
        if 'power series' in t and 'function' in t: return 'Represent the function as a power series.'
        if 'taylor' in t and 'apps' not in t: return 'Find the Taylor series for the function about the given point.'
        if 'apps' in t or 'applications' in t: return 'Use series to solve the problem.'
        if 'binomial' in t: return 'Use the Binomial Series to expand the function.'
        return 'Solve the following problem.'
    return 'Solve the following problem.'


def main(verify=False):
    all_sections = {}
    for path in MD_FILES:
        secs = parse_md_file(path)
        for s in secs:
            all_sections[s['id']] = s
    # Add the synthesized Calc I Ch 6 sections for U2 coverage
    for s in build_calc1_sections_from_csv():
        all_sections[s['id']] = s

    # Sort by section numeric order for stable JSON
    ordered = {}
    for key in sorted(all_sections.keys(), key=lambda k: tuple(int(x) for x in k.split('.'))):
        ordered[key] = all_sections[key]

    with open(OUT_PATH, 'w') as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)

    print(f'Wrote {OUT_PATH}')
    total_probs = sum(len(s['problems']) for s in ordered.values())
    print(f'Sections: {len(ordered)}')
    print(f'Problems: {total_probs}')
    if verify:
        print('\nPer-section breakdown:')
        for sid, s in ordered.items():
            print(f'  {sid} [{s["chapterNum"]}] {s["title"]} — {len(s["problems"])} problems')


if __name__ == '__main__':
    main(verify='--verify' in sys.argv)
