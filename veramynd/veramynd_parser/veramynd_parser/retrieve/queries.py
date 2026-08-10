"""Focused multi-intent lesson queries for enterprise K-12 retrieval.

Curriculum-agnostic: reads common normalized lesson fields (objective, skills,
student/teacher actions, vocabulary, evidence) without publisher-specific IDs.

Bridges abstract standards language ↔ classroom language (architecture §7):
domain bridge cues + student-action priority over noisy evidence floods.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Lower = higher priority when trimming to max_queries.
_SOURCE_PRIORITY: dict[str, int] = {
    "learning_target": 0,
    "objective": 1,
    # Standard-language bridges for acts that classroom prose understates
    # (present-clearly, create-poem, word-parts). Keep ahead of generic skills.
        "competency_present_ideas": 1,
    "competency_create_poem": 1,
    "competency_word_parts": 1,
    "competency_context_clues": 1,
    "competency_make_predictions": 1,
    "competency_make_inferences": 1,
    "competency_dialogue_qa": 1,
    "competency_descriptive_words": 1,
    "competency_research_questions": 1,
    "competency_acquire_vocabulary": 1,
    "competency_use_text_evidence": 1,
    "competency_story_elements": 1,
    "skill": 2,
    "instructional_purpose": 3,
    "student_action": 4,
    "vocabulary": 5,
    "discussion_prompt": 6,
    "writing_task": 6,
    "reading_task": 6,
    "domain_bridge": 7,
    "domain": 8,
    "assessment": 9,
    "evidence": 10,
    "teacher_action": 11,
    "protocols": 12,
    "title": 13,
}

# Curriculum-agnostic: if lesson text shows the classroom signal, inject a
# retrieval arm in standards-like wording so dense+BM25 hit the leaf embeds.
# (signal_tokens, source, bridge_text)
_COMPETENCY_BRIDGES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        (
            "present ideas",
            "share observations",
            "share orally",
            "sentence frame",
            "sentence frames",
            "oral_production",
            "picture tea party",
            "back-to-back",
            "face-to-face",
            "communicate clearly",
            "present to",
        ),
        "competency_present_ideas",
        (
            "Students communicate clearly to present ideas, information, and texts "
            "aloud to audiences and peers using spoken language and sentence frames. "
            "Standard skill: present ideas information texts clearly in oral communication."
        ),
    ),
    (
        (
            "poem",
            "poems",
            "poetic",
            "rhyme",
            "rhyming",
            "narrative poem",
            "write their own",
            "own version of verse",
            "write a narrative poem",
            "what the moon sees",
            "create poems",
            "create poem",
            # bare "verse/verses" omitted: common in close-read language dives
            # without student poem construction (e.g. G1M2U1L6).
        ),
        "competency_create_poem",
        (
            "Students use poetic techniques to create poems using simple words "
            "and phrases that may or may not rhyme; write original poem verses independently. "
            "Standard skill: create poems with poetic techniques simple words phrases."
        ),
    ),
    (
        (
            "word parts",
            "word-part",
            "unfamiliar word",
            "unfamiliar words",
            "unknown word",
            "multiple-meaning",
            "multiple meaning",
            "context clue",
            "context clues",
            "morphology",
            "prefix",
            "suffix",
            "root word",
            "mini language dive",
            "what does the word",
            "what two words",
            "vocabulary words",
            "word wall",
            "word walls",
            "explain meanings",
            "explain meaning",
            "meaning of",
            "meanings of",
        ),
        "competency_word_parts",
        (
            "Students determine the meanings of unfamiliar words and concepts by "
            "applying knowledge of context and of academic vocabulary and word parts. "
            "Standard skill: use context and word parts to unlock unknown words."
        ),
    ),
    # Distinct from word-parts / morphology (EICC.3.g): pure context-clue leaves
    # (L.V.3.a) need official "within and beyond a sentence" wording.
    (
        (
            "what does the word",
            "what does the word mean",
            "mean in this chunk",
            "context clue",
            "context clues",
            "multiple-meaning",
            "multiple meaning",
            "unknown word",
            "unknown words",
            "clarify the meaning",
            "clarify meaning",
            "mini language dive",
        ),
        "competency_context_clues",
        (
            "Students use context within and beyond a sentence to determine or "
            "clarify the meaning of unknown and multiple-meaning words and phrases. "
            "Standard skill: use surrounding sentence and text context as clues "
            "to word meaning."
        ),
    ),
    (
        (
            "predict",
            "prediction",
            "predictions",
            "what will happen",
            "what happens next",
            "likely to come next",
            "make and track",
            "track predictions",
            "forecast",
            # Classroom predict prompts rarely say "predict" (EL title / ending talk).
            "what do you think",
            "do you think",
            "where do you think",
            "based on the title",
            "end of the story",
            "story will be about",
            "think this story",
            "think the end",
        ),
        "competency_make_predictions",
        (
            "Students make and track predictions about events and information "
            "likely to come next in a text based on titles, illustrations, and "
            "what they have already read. "
            "Standard skill: make and track predictions about upcoming events."
        ),
    ),
    (
        (
            "infer",
            "inference",
            "inferences",
            "levels of meaning",
            "what does this verse mean",
            "what does the verse mean",
            "verse mean",
            "verse means",
            "now what do you think the verse",
            "what does this mean",
            "different levels of meaning",
            "support inferences",
            "make inferences",
        ),
        "competency_make_inferences",
        (
            "Students make, track, and support inferences about different levels "
            "of meaning within the text using evidence from the text. "
            "Standard skill: make inferences about meaning beyond the exact words."
        ),
    ),
    (
        (
            "ask and answer",
            "asking and answering",
            "ask questions",
            "answer questions",
            "invite responses",
            "total participation",
            "dialogue with audiences",
            "engage in dialogue",
            # Intentionally omit turn-and-talk / elbow-partner alone — common
            # protocols that flood Speaking leaves without a true Q&A act.
        ),
        "competency_dialogue_qa",
        (
            "Students engage in dialogue with audiences by asking and answering "
            "questions during discussion and close read-aloud. "
            "Standard skill: ask and answer questions in oral dialogue with peers."
        ),
    ),
    (
        (
            "descriptive words",
            "words that describe",
            "describe the sun",
            "describe the moon",
            "words that describe the",
            "underline the words",
            "listen carefully for words",
            "words that paint",
            "adjectives",
        ),
        "competency_descriptive_words",
        (
            "Students identify and explain the use of descriptive words in texts; "
            "notice words that describe people, places, and things in songs and stories. "
            "Standard skill: identify descriptive words and explain how they are used."
        ),
    ),
    (
        (
            "i wonder",
            "i notice",
            "noticing and wondering",
            "notices and wonders",
            "wonder about",
            "ask questions about what i notice",
            "topics of interest",
            "for research",
            "question words",
            "research questions",
        ),
        "competency_research_questions",
        (
            "Students ask questions about topics of interest for research; write wonders "
            "using question words about pictures, videos, and outdoor observations. "
            "Standard skill: ask research questions about topics of interest."
        ),
    ),
    (
        (
            "word wall",
            "word walls",
            "vocabulary cards",
            "vocabulary words",
            "academic vocabulary",
            "specialized vocabulary",
            "acquire and apply",
            "new vocabulary",
            "repeat the word",
            "gesture as they repeat",
        ),
        "competency_acquire_vocabulary",
        (
            "Students acquire and apply general, academic, and specialized vocabulary "
            "words and phrases through grade-level texts and content using word walls "
            "and oral practice. "
            "Standard skill: acquire and apply vocabulary from grade-level content."
        ),
    ),
    (
        (
            "refer to",
            "cite",
            "text evidence",
            "evidence from",
            "parts of texts",
            "support an idea",
            "support their",
            "key details",
            "using details",
            "from the text",
        ),
        "competency_use_text_evidence",
        (
            "Students refer to parts of texts when supporting an idea, answer, or opinion. "
            "Standard skill: use specific parts of texts to support ideas and answers."
        ),
    ),
    (
        (
            "character",
            "characters",
            "traits",
            "setting",
            "settings",
            "story structure",
            "major events",
            "plot",
            "retell",
            "story elements",
            "beginning middle end",
            "describe the",
            "main character",
            "what is the boy doing",
            "main characters",
            "character traits",
            "central message",
        ),
        "competency_story_elements",
        (
            "Students describe characters, settings, and major events in a story using "
            "key details; describe traits of the main characters and how their words "
            "and actions support the central message of the story. "
            "Standard skill: describe story structure and character traits with details."
        ),
    ),
)

_DEFAULT_MAX_SKILLS = 8
_DEFAULT_MAX_STUDENT_ACTIONS = 4
_DEFAULT_MAX_TEACHER_ACTIONS = 0
_MAX_QUERY_CHARS = 360

# Shared pedagogical cues — framework-neutral classroom language that mirrors
# how NormalizedStandard competency / pedagogy_terms are written.
_DOMAIN_BRIDGES: dict[str, str] = {
    "Vocabulary": (
        "Students acquire and apply vocabulary words and phrases; "
        "use context to determine or clarify word meaning."
    ),
    "Language": (
        "Students use language and word knowledge to understand texts "
        "and express ideas clearly."
    ),
    "Speaking & Listening": (
        "Students communicate ideas clearly in discussion and presentation; "
        "listen and respond to peers; share observations and questions orally."
    ),
    "Comprehension": (
        "Students understand texts; describe and retell events; "
        "ask and answer questions; make and track predictions; make inferences; "
        "make meaning and support ideas with evidence."
    ),
    "Writing": (
        "Students write and draw to record ideas, observations, "
        "responses, and learning; compose verses and poems with simple words and phrases."
    ),
    "Reading": (
        "Students read and comprehend grade-level texts; "
        "identify key details and explain understanding."
    ),
}


def _clean(s: Any) -> str:
    return " ".join(str(s or "").split()).strip()


def _source_priority(source: str) -> int:
    if source in _SOURCE_PRIORITY:
        return _SOURCE_PRIORITY[source]
    if source.startswith("competency_"):
        return 1
    if source.startswith("skill_"):
        return _SOURCE_PRIORITY["skill"]
    if source.startswith("learning_target_"):
        return _SOURCE_PRIORITY["learning_target"]
    if source.startswith("evidence_"):
        return _SOURCE_PRIORITY["evidence"]
    if source.startswith("discussion_prompt_"):
        return _SOURCE_PRIORITY["discussion_prompt"]
    if source.startswith("writing_task_"):
        return _SOURCE_PRIORITY["writing_task"]
    if source.startswith("reading_task_"):
        return _SOURCE_PRIORITY["reading_task"]
    return 10


def _lesson_signal_blob(data: dict[str, Any]) -> str:
    """Flatten high-signal normalized fields for competency-bridge matching."""
    parts: list[str] = []
    for key in ("objective", "title", "instructional_purpose", "lesson_purpose", "purpose"):
        parts.append(_clean(data.get(key)))
    for item in data.get("what_is_taught") or []:
        if isinstance(item, dict):
            parts.append(_clean(item.get("skill")))
        else:
            parts.append(_clean(item))
    for target in _text_items(
        data.get("learning_targets") or data.get("learning_target"),
        keys=("text", "target", "objective", "description"),
    )[:6]:
        parts.append(target)
    for line in _action_lines(data.get("student_actions"), limit=12):
        parts.append(line)
    for line in _action_lines(data.get("teacher_actions"), limit=4):
        parts.append(line)
    vocab = data.get("vocabulary") or {}
    if isinstance(vocab, dict):
        for bucket in ("new", "review"):
            for word in vocab.get(bucket) or []:
                parts.append(_clean(word))
    for item in (data.get("evidence") or [])[:40]:
        if isinstance(item, dict):
            parts.append(_clean(item.get("quote") or item.get("text")))
        else:
            parts.append(_clean(item))
    for field in (
        "discussion_prompts",
        "writing_tasks",
        "reading_tasks",
        "protocols_routines",
    ):
        for value in _text_items(
            data.get(field),
            keys=("text", "prompt", "task", "description", "summary"),
        )[:4]:
            parts.append(value)
    return " ".join(p for p in parts if p).lower()


def _competency_bridges_for_lesson(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(source, text)`` bridges whose signals appear in the lesson."""
    blob = _lesson_signal_blob(data)
    if not blob:
        return []
    out: list[tuple[str, str]] = []
    for tokens, source, text in _COMPETENCY_BRIDGES:
        if any(tok in blob for tok in tokens):
            out.append((source, text))
    return out


def _action_lines(actions: Any, *, limit: int = 8) -> list[str]:
    if limit < 1:
        return []
    if isinstance(actions, list):
        out: list[str] = []
        for item in actions:
            if isinstance(item, dict):
                text = _clean(
                    item.get("text")
                    or item.get("action")
                    or item.get("description")
                    or item.get("task")
                )
            else:
                text = _clean(item)
            if text and text.upper() != "NONE OBSERVED":
                out.append(text)
            if len(out) >= limit:
                break
        return out
    if not isinstance(actions, dict):
        text = _clean(actions)
        return [text] if text and text.upper() != "NONE OBSERVED" else []
    out: list[str] = []
    for key, val in actions.items():
        if key == "domain_specific":
            continue
        if isinstance(val, dict):
            continue
        values = _text_items(
            val,
            keys=("text", "action", "description", "task", "prompt"),
        )
        for value in values:
            if not value or value.upper() == "NONE OBSERVED":
                continue
            out.append(f"{key}: {value}")
            if len(out) >= limit:
                return out
    return out


def _skill_focus(skill: str, *, max_words: int = 12) -> str:
    """Prefer transferable skill head for retrieval overlap with standards."""
    words = _clean(skill).split()
    if not words:
        return ""
    return " ".join(words[:max_words])


def _concise(text: Any, *, max_chars: int = _MAX_QUERY_CHARS) -> str:
    """Normalize a retrieval arm and bound long publisher prose."""
    value = _clean(text)
    if len(value) <= max_chars:
        return value
    clipped = value[:max_chars]
    cut = max(clipped.rfind(". "), clipped.rfind("? "), clipped.rfind("; "))
    if cut >= max_chars // 2:
        clipped = clipped[: cut + 1]
    else:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _query_tokens(text: str) -> set[str]:
    boilerplate = {
        "classroom",
        "discussion",
        "evidence",
        "lesson",
        "learn",
        "objective",
        "practice",
        "prompt",
        "required",
        "student",
        "students",
        "target",
        "task",
        "teacher",
        "will",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in boilerplate
    }


def _is_near_duplicate(text: str, prior: list[str]) -> bool:
    """Deterministic lexical dedupe for repeated normalized lesson fields."""
    key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    tokens = _query_tokens(text)
    for old in prior:
        old_key = re.sub(r"[^a-z0-9]+", " ", old.lower()).strip()
        if key == old_key:
            return True
        old_tokens = _query_tokens(old)
        if not tokens or not old_tokens:
            continue
        overlap = len(tokens & old_tokens)
        union = len(tokens | old_tokens)
        smaller = min(len(tokens), len(old_tokens))
        if union and overlap / union >= 0.88:
            return True
        if smaller and overlap / smaller >= 0.88:
            return True
    return False


def _text_items(value: Any, *, keys: tuple[str, ...] = ()) -> list[str]:
    """Read common scalar/list/object text shapes without publisher assumptions."""
    if isinstance(value, str):
        return [_clean(value)] if _clean(value) else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_text_items(item, keys=keys))
        return out
    if isinstance(value, dict):
        for key in keys:
            text = _clean(value.get(key))
            if text:
                return [text]
        out = []
        for key, item in value.items():
            if key in {"domain_specific", "metadata", "provenance"}:
                continue
            if isinstance(item, str):
                text = _clean(item)
                if text and text.upper() != "NONE OBSERVED":
                    out.append(text)
        return out
    return []


def grade_from_normalize(path: Path | str) -> int | None:
    """Extract lesson grade from NormalizedLesson (provenance / level / id)."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    prov = data.get("provenance") or {}
    if isinstance(prov, dict):
        raw = prov.get("grade")
        if raw is not None and str(raw).strip() != "":
            try:
                return int(str(raw).strip())
            except ValueError:
                pass
    level = _clean(data.get("level"))
    m = re.search(r"(?i)\bgrade\s*(\d+)\b", level)
    if m:
        return int(m.group(1))
    rid = _clean(data.get("resource_id") or p.stem)
    m = re.match(r"(?i)^G(\d+)", rid)
    if m:
        return int(m.group(1))
    return None


def domains_from_normalize(path: Path | str) -> list[str]:
    """Primary + secondary domains from a NormalizedLesson (order preserved)."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    domain = data.get("domain") or {}
    out: list[str] = []
    if isinstance(domain, dict):
        primary = _clean(domain.get("primary"))
        if primary:
            out.append(primary)
        for item in domain.get("secondary") or []:
            name = _clean(item)
            if name and name not in out:
                out.append(name)
    return out


def skill_focus_text_from_normalize(path: Path | str) -> str:
    """High-signal lesson requirements for lexical shortlist prior.

    Newline-separated so shortlist skill scoring can max over fragments
    (objective / targets / taught skills) without bag-dilution.
    Feedback-style student actions are omitted — they favor generic
    collaboration standards over content standards.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    parts: list[str] = []
    objective = _clean(data.get("objective"))
    if objective:
        parts.append(objective)
    for target in _text_items(
        data.get("learning_targets") or data.get("learning_target"),
        keys=("text", "target", "objective", "description"),
    )[:6]:
        parts.append(target)
    for item in data.get("what_is_taught") or []:
        skill = _clean(item.get("skill")) if isinstance(item, dict) else _clean(item)
        if skill:
            parts.append(_skill_focus(skill, max_words=16) or skill)
    vocab = data.get("vocabulary") or {}
    if isinstance(vocab, dict):
        words = [
            _clean(word)
            for word in (vocab.get("new") or []) + (vocab.get("review") or [])
            if _clean(word)
        ]
        if words:
            parts.append(" ".join(words[:16]))
    return "\n".join(parts).strip()


def query_arm_weight(source: str) -> float:
    """Relative multi-query RRF weight for a focused query source."""
    if source.startswith("learning_target_"):
        return 1.75
    if source == "objective":
        return 1.7
    # Hard construction / present-clearly leaves need room against noisy dialogue/vocab.
    if source == "competency_create_poem":
        # One strong poem arm must beat multi-arm breadth so independent verse
        # construction (1.T.T.4.b) lands in the top-20 with merge_top_arms=3.
        return 5.0
    if source == "competency_present_ideas":
        return 2.7
    if source in {
        "competency_descriptive_words",
        "competency_story_elements",
        "competency_research_questions",
        "competency_acquire_vocabulary",
    }:
        return 2.55
    if source == "competency_dialogue_qa":
        # Q&A act is real but high weight floods Speaking leaves.
        return 1.6
    if source.startswith("competency_"):
        # Align arms to standard competency phrasing — outrank skill arms when
        # a single competency hit must lift a buried leaf into merge top-50.
        return 2.2
    if source == "instructional_purpose":
        return 1.55
    if source == "domain":
        return 0.85
    if source == "domain_bridge":
        return 0.8
    if source.startswith("skill_"):
        return 1.8
    if source == "vocabulary":
        return 1.6
    if source == "student_action":
        return 1.45
    if source.startswith(("discussion_prompt_", "writing_task_", "reading_task_")):
        return 1.5
    if source.startswith("evidence_"):
        return 0.4
    if source == "assessment":
        return 0.95
    if source == "protocols":
        return 0.4
    if source == "teacher_action":
        return 0.3
    return 1.0


def query_counts_for_coverage(source: str) -> bool:
    """Whether a query arm contributes to precise multi-query coverage."""
    if source.startswith(
        (
            "learning_target_",
            "skill_",
            "competency_",
            "discussion_prompt_",
            "writing_task_",
            "reading_task_",
        )
    ):
        return True
    return source in {
        "objective",
        "instructional_purpose",
        "vocabulary",
        "student_action",
    }


def focused_queries_from_normalize(
    path: Path | str,
    *,
    max_queries: int = 24,
    max_evidence: int = 1,
    max_skills: int = _DEFAULT_MAX_SKILLS,
    max_student_actions: int = _DEFAULT_MAX_STUDENT_ACTIONS,
    max_teacher_actions: int = _DEFAULT_MAX_TEACHER_ACTIONS,
) -> list[dict[str, str]]:
    """Build focused retrieval queries from a NormalizedLesson JSON.

    Each item is ``{"query_id", "source", "text"}``. Deduplicates near-identical
    texts. High-signal fields (objective, domain bridges, skills, student
    actions, vocabulary) are preferred when trimming to ``max_queries``.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    rid = _clean(data.get("resource_id") or p.stem) or p.stem
    queries: list[dict[str, str]] = []

    accepted_texts: list[str] = []

    def add(source: str, text: str) -> None:
        t = _concise(text)
        if len(t) < 12:
            return
        if _is_near_duplicate(t, accepted_texts):
            return
        accepted_texts.append(t)
        queries.append(
            {
                "query_id": f"{rid}#{source}#{len(queries)+1}",
                "source": source,
                "text": t,
            }
        )

    learning_targets = _text_items(
        data.get("learning_targets") or data.get("learning_target"),
        keys=("text", "target", "objective", "description"),
    )
    for i, target in enumerate(learning_targets[:4], start=1):
        add(f"learning_target_{i}", f"Students will: {target}")

    objective = _clean(data.get("objective"))
    if objective:
        add("objective", f"Lesson objective: {objective}")

    # Standard-language arms when lesson signals imply under-lexicalized acts
    # (oral present-clearly, create poems, word-parts meaning).
    for source, bridge_text in _competency_bridges_for_lesson(data):
        add(source, bridge_text)

    purpose = _text_items(
        data.get("instructional_purpose")
        or data.get("lesson_purpose")
        or data.get("purpose"),
        keys=("summary", "description", "text", "purpose"),
    )
    if purpose:
        add("instructional_purpose", f"Instructional purpose: {purpose[0]}")

    domain = data.get("domain") or {}
    domain_names: list[str] = []
    if isinstance(domain, dict):
        primary = _clean(domain.get("primary"))
        secondary = [
            _clean(x)
            for x in (domain.get("secondary") or [])
            if _clean(x)
        ]
        if primary:
            domain_names.append(primary)
            bits = [f"Domain primary: {primary}"]
            if secondary:
                bits.append(f"Domain secondary: {', '.join(secondary)}")
            add("domain", " | ".join(bits))
        domain_names.extend(secondary)

    # Pedagogical bridges: primary domain only (secondary bridges flood
    # multi-domain lessons with generic Vocabulary/Language arms).
    primary_name = domain_names[0] if domain_names else ""
    if primary_name:
        bridge = _DOMAIN_BRIDGES.get(primary_name)
        if not bridge:
            for key, val in _DOMAIN_BRIDGES.items():
                if key.lower() == primary_name.lower():
                    bridge = val
                    break
        if bridge:
            add(
                "domain_bridge",
                f"Pedagogical focus — {primary_name}: {bridge}",
            )

    skills: list[str] = []
    for item in data.get("what_is_taught") or []:
        if isinstance(item, dict):
            skill = _clean(item.get("skill"))
            if skill:
                skills.append(skill)
        elif isinstance(item, str) and _clean(item):
            skills.append(_clean(item))
    for i, skill in enumerate(skills[: max(0, max_skills)], start=1):
        focus = _skill_focus(skill)
        add(f"skill_{i}", f"Students learn / practice: {focus or skill}")

    for line in _action_lines(
        data.get("student_actions"), limit=max(0, max_student_actions)
    ):
        add(
            "student_action",
            f"Required student action — {line}",
        )

    task_fields: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "discussion_prompt",
            ("discussion_prompts", "discussion_questions", "prompts_for_discussion"),
        ),
        ("writing_task", ("writing_tasks", "writing_task", "written_tasks")),
        ("reading_task", ("reading_tasks", "reading_task", "texts_and_tasks")),
    )
    for source, field_names in task_fields:
        values: list[str] = []
        for field_name in field_names:
            values.extend(
                _text_items(
                    data.get(field_name),
                    keys=("text", "prompt", "task", "description", "summary"),
                )
            )
        # Normalized lessons commonly encode task modality in structured
        # student-action slots instead of top-level task arrays.
        student_actions = data.get("student_actions") or {}
        if isinstance(student_actions, dict):
            action_keys = {
                "discussion_prompt": ("oral_production", "reasoning_explanation"),
                "writing_task": ("written_production",),
                "reading_task": ("comprehension_response",),
            }[source]
            for action_key in action_keys:
                action_text = _clean(student_actions.get(action_key))
                if action_text and action_text.upper() != "NONE OBSERVED":
                    values.append(action_text)
        for i, value in enumerate(values[:3], start=1):
            add(f"{source}_{i}", f"{source.replace('_', ' ').title()}: {value}")

    vocab = data.get("vocabulary") or {}
    if isinstance(vocab, dict):
        new_v = [_clean(x) for x in (vocab.get("new") or []) if _clean(x)]
        review_v = [_clean(x) for x in (vocab.get("review") or []) if _clean(x)]
        words = new_v + review_v
        if words:
            add(
                "vocabulary",
                "Vocabulary targets (acquire / apply / clarify meaning): "
                + "; ".join(words[:12]),
            )

    assessment = data.get("assessment")
    if isinstance(assessment, dict):
        atext = _clean(
            assessment.get("summary")
            or assessment.get("description")
            or assessment.get("task")
        )
        if atext:
            add("assessment", f"Assessment / task: {atext}")
    elif isinstance(assessment, str) and _clean(assessment):
        add("assessment", f"Assessment / task: {_clean(assessment)}")

    evidence_bits: list[str] = []
    evidence_tasks: dict[str, list[str]] = {
        "discussion_prompt": [],
        "writing_task": [],
        "reading_task": [],
    }
    # Task classification scans ALL evidence (bounded); only the generic
    # evidence_bits list is capped by max_evidence. Breaking the whole loop at
    # max_evidence=1 meant a writing quote sitting at evidence[1] never got its
    # writing_task arm despite the [:2] slice below expecting up to two.
    for item in (data.get("evidence") or [])[:12]:
        if not isinstance(item, dict):
            continue
        quote = _clean(item.get("quote") or item.get("text"))
        if not quote:
            continue
        if len(evidence_bits) < max_evidence:
            evidence_bits.append(quote)
        role = _clean(item.get("evidence_role")).lower()
        supported = {
            _clean(x).lower() for x in (item.get("supports_action") or []) if _clean(x)
        }
        if role == "elicitation_check" or "oral_production" in supported:
            evidence_tasks["discussion_prompt"].append(quote)
        if "written_production" in supported:
            evidence_tasks["writing_task"].append(quote)
        if "comprehension_response" in supported:
            evidence_tasks["reading_task"].append(quote)
    for source, values in evidence_tasks.items():
        for i, value in enumerate(values[:2], start=1):
            # "_evidence_" keeps these labels distinct from the task-field arms
            # above (both used to emit discussion_prompt_1, making per-arm
            # diagnostics ambiguous); _source_priority matches by prefix.
            add(
                f"{source}_evidence_{i}",
                f"{source.replace('_', ' ').title()}: {value}",
            )
    for i, quote in enumerate(evidence_bits, start=1):
        add(f"evidence_{i}", f"Classroom evidence / prompt: {quote[:400]}")

    protocols = data.get("protocols_routines") or []
    if isinstance(protocols, list):
        proto = [_clean(x) for x in protocols if _clean(x)]
        if proto:
            add("protocols", "Protocols / routines: " + "; ".join(proto[:6]))

    for line in _action_lines(
        data.get("teacher_actions"), limit=max(0, max_teacher_actions)
    ):
        add("teacher_action", f"Teacher action — {line}")

    # Last-resort cascade. Each `add` can silently drop too-short text, so
    # re-check `queries` after every attempt — an `elif` chain here used to
    # return [] for a record whose only field was a short objective, producing
    # a misleading "no non-empty queries" error far downstream instead of the
    # diagnostic below.
    if not queries:
        title = _clean(data.get("title"))
        if title:
            add("title", f"Lesson: {title}")
    if not queries and objective:
        add("objective", objective)
    if not queries:
        raise ValueError(f"{p}: no usable fields for focused retrieval queries")

    ranked = sorted(
        enumerate(queries),
        key=lambda iv: (_source_priority(iv[1]["source"]), iv[0]),
    )
    selected = ranked[: max(1, max_queries)]
    selected.sort(key=lambda iv: (_source_priority(iv[1]["source"]), iv[0]))
    out: list[dict[str, str]] = []
    for i, (_orig_i, q) in enumerate(selected, start=1):
        out.append(
            {
                "query_id": f"{rid}#{q['source']}#{i}",
                "source": q["source"],
                "text": q["text"],
            }
        )
    return out


def rerank_context_from_normalize(path: Path | str, *, max_chars: int = 1800) -> str:
    """Structured lesson context for the unchanged cross-encoder.

    Unlike dense retrieval, CE reranking benefits from one coherent view. Keep
    skills and requirements first so tokenizer truncation removes low-priority
    context rather than the pedagogical match signal.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    parts: list[str] = []
    for key in ("title", "objective"):
        value = _clean(data.get(key))
        if value:
            parts.append(f"[{key.upper()}] {_concise(value, max_chars=320)}")

    targets = _text_items(
        data.get("learning_targets") or data.get("learning_target"),
        keys=("text", "target", "objective", "description"),
    )
    if targets:
        parts.append("[LEARNING TARGETS] " + "; ".join(targets[:3]))

    skills = []
    for item in data.get("what_is_taught") or []:
        skill = _clean(item.get("skill")) if isinstance(item, dict) else _clean(item)
        if skill:
            skills.append(_skill_focus(skill, max_words=14) or skill)
    if skills:
        parts.append("[SKILLS] " + "; ".join(skills[:8]))

    purpose = _text_items(
        data.get("instructional_purpose")
        or data.get("lesson_purpose")
        or data.get("purpose"),
        keys=("summary", "description", "text", "purpose"),
    )
    if purpose:
        parts.append(f"[INSTRUCTIONAL PURPOSE] {_concise(purpose[0], max_chars=280)}")

    student_actions = _action_lines(data.get("student_actions"), limit=4)
    if student_actions:
        parts.append("[STUDENT ACTIONS] " + "; ".join(student_actions))

    for source, fields in (
        ("DISCUSSION", ("discussion_prompts", "discussion_questions")),
        ("WRITING", ("writing_tasks", "writing_task")),
        ("READING", ("reading_tasks", "reading_task")),
    ):
        values: list[str] = []
        for field in fields:
            values.extend(
                _text_items(
                    data.get(field),
                    keys=("text", "prompt", "task", "description", "summary"),
                )
            )
        if values:
            parts.append(f"[{source} TASKS] " + "; ".join(values[:2]))

    vocab = data.get("vocabulary") or {}
    if isinstance(vocab, dict):
        words = [
            _clean(word)
            for word in (vocab.get("new") or []) + (vocab.get("review") or [])
            if _clean(word)
        ]
        if words:
            parts.append("[VOCABULARY] " + "; ".join(words[:12]))

    evidence = []
    for item in data.get("evidence") or []:
        if isinstance(item, dict):
            quote = _clean(item.get("quote") or item.get("text"))
            if quote:
                evidence.append(_concise(quote, max_chars=180))
        if len(evidence) >= 1:
            break
    if evidence:
        parts.append("[EVIDENCE / PROMPTS] " + " | ".join(evidence))

    domain = data.get("domain") or {}
    if isinstance(domain, dict):
        primary = _clean(domain.get("primary"))
        secondary = [_clean(x) for x in (domain.get("secondary") or []) if _clean(x)]
        names = [name for name in [primary, *secondary] if name]
        if names:
            parts.append("[DOMAINS] " + "; ".join(names))

    text = "\n".join(parts).strip()
    if not text:
        raise ValueError(f"{path}: empty rerank context")
    return text[:max_chars]


__all__ = [
    "domains_from_normalize",
    "focused_queries_from_normalize",
    "grade_from_normalize",
    "query_arm_weight",
    "query_counts_for_coverage",
    "rerank_context_from_normalize",
    "skill_focus_text_from_normalize",
]
