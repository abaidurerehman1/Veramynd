# GA Grade 1 — Gold Set (Batch 1, grounded in real curriculum)

**Framework:** Georgia K-12 ELA Standards, Grade 1 (2023)  
**Curriculum:** EL Education Grade 1, Module 2: The Sun, Moon, and Stars (Teacher Guide)  
**Engine:** Standards Alignment Classifier v1 \+ GA Grade 1 overlay

**Records:** 24  ·  full: 6 · partial: 14 · none (known-negatives): 4  
**Standards covered:** 18 substandards across all four GA domains (Foundations light — this is a literature/content module)  
**Status:** all labels SME-confirmed. Rulings R1–R3 locked (see below).

> Every quote below is verbatim from the EL Grade 1 Module 2 Teacher Guide, with the EL Education page number. Labels apply the official GA Grade 1 standard text (not the CCSS codes the curriculum prints). `sme_review_flag` marks the borderline calls that most need Liz's sign-off.

## How to read a record

Each record is one `(lesson, standard)` pair — the unit of the Veramynd gold set (§16). `matched_status` is the gold label; `clauses[]` is the SME reasoning (which clause, which actor) that justifies it and lets you report per-class error by clause; `hard_case_type` stratifies the set.

## SME rulings (locked)

**R1 — A read-aloud counts as a grade-level text.** For (I) Interpretation substandards that require 'grade-level texts' (vocabulary, comprehension), a teacher read-aloud of a grade-level text satisfies the 'grade-level texts' channel at grades K–1, where students are emergent decoders (the curriculum states this outright: 'Primary learners need to hear many texts read aloud in order to build their word and world knowledge'). The student-actor gate still applies to the skill itself — the student must do the acquiring/inferring; mere presence of a word in the read-aloud is only exposure. SME-confirmed; applied uniformly below. *Rationale for the coverage this unlocks: nearly every comprehension/vocab match in this read-aloud-based module rides on this ruling.*

**R3 — Core vs. supplemental content (curriculum-agnostic); supplemental caps at PARTIAL.** *Definition (publisher-independent):* **core** content is the main instructional sequence delivered to every student; **supplemental** content is any segment that is conditional, optional, or targeted to a subset of students. *Operational test:* would a student following the main lesson as written necessarily perform this act? Yes → core; reached only if a condition fires, an option is elected, or a specific subgroup is served → supplemental. *Signals (not a fixed heading list):* conditional/optional language ('if…', 'as needed', 'consider…', 'optional', 'extension', 'challenge', 'early finishers'); subgroup targeting ('for English learners', 'for students who need more/less support'); structural placement outside the main sequence (sidebars, margin notes, callouts). *Ruling:* a standard's act performed ONLY in supplemental content caps the record at **partial** — the student genuinely performs it (real coverage → not none), but it is not the core instruction every student receives (→ not full); this is the engine's existing 'optional or extension-only task caps at partially met' rule. If the act ALSO appears in core, core governs. *Per-curriculum instantiation:* the specific markers vary by publisher and live in the parser config / overlay, NOT in this rule — in THIS curriculum (EL Education) they are 'For ELLs', 'Meeting Students' Needs', 'Mini Language Dive', and the UDL notes (MMR/MMAE/MME). Every record carries a `content_tier` \= core | supplemental tag so this is auditable.

**R2 — Decomposing a list joined by 'and'/'or' (split vs. OR).** Two questions, in order. (1) Are the listed items different cognitive **operations**? If yes, split into separate required clauses (ask/answer; blend/segment; determine-an-unknown-word vs. disambiguate-a-multiple-meaning-word). (2) If it's the **same operation across several targets**, split only when the targets are **complementary** — each distinct and needed, so missing one is a real gap ('characters, settings, and major events'); treat as **OR** (any one \= full) when the targets are **interchangeable/redundant** members of one category ('thoughts, feelings, and ideas'; 'general, academic, and specialized' vocabulary; 'ideas, information, and texts'). *Heuristic for question 2:* if a lesson covered only one listed item, would an expert say the skill was fully taught (→ interchangeable, OR) or that something important was missing (→ complementary, split)? *Scope:* the test is `[engine]`; which specific lists are complementary vs. interchangeable is a `[framework]` overlay note.

---

## Note for the engineer (core vs. supplemental — parser \+ judge must agree)

Teacher guides put real instruction in two tiers: the **core lesson** (the main sequence every student does) and **supplemental** content (conditional / optional / subgroup-targeted differentiation). This is defined functionally (see R3), so it generalizes across publishers — only the surface markers change. Ruling R3 caps supplemental-only matches at partial. Three consequences for the pipeline:

1. **Classify tier during normalization, generically.** The parser (Stage 1–3) should emit a `content_tier` (core | supplemental) per lesson segment using the publisher-independent signals in R3 (conditional/optional language, subgroup targeting, out-of-sequence placement) PLUS a small per-publisher marker map (e.g. EL Education → 'For ELLs' / 'Meeting Students' Needs' / 'Mini Language Dive' / UDL). Keep the generic test as the fallback so a new curriculum works before anyone hand-writes its marker map; flag ambiguous or inline-differentiation cases for human review.  
     
2. **Parsing scope and the judge must agree.** If the parser feeds supplemental text into the lesson passed to the judge, the judge must apply the R3 cap; if the parser strips it, those matches disappear entirely (score none/absent). Either is defensible, but it must be *one* policy, set once — otherwise you get silent inconsistency between what was extracted and how it was scored. The gold `content_tier` tag lets you test whichever policy you pick.  
     
3. **This is a product-definition call.** 'Does this lesson teach standard X?' means either (a) *anywhere in the lesson as written, incl. differentiation* → supplemental counts, capped at partial (the policy encoded here); or (b) *what the core lesson teaches every student* → supplemental-only \= not core. Pick (a) or (b) before scaling the gold set, because it systematically changes labels.

---

### `GA1-M2-016` — `1.L.V.1.a` (I) → **FULL**  ·  *anchor\_full\_acquire\_apply*

**Standard:** Acquire and apply general, academic, and specialized vocabulary words and phrases through grade-level texts and content.  
**Lesson:** Unit 1, Lesson 1 (swept across the lesson): read-aloud \+ Word Wall \+ Back-to-Back \+ independent writing — p. 44-49 · tier: **core**

> \[p44, read-aloud of 'Elvin'\] 'What does Elvin observe about the sun?' \-- students discuss the sun as it appears in the grade-level text read aloud. \[p45, Word Wall\] Show the card for sun; students repeat the word with a gesture; teacher defines it and uses it in a sentence (repeated for moon, star). \[p48, Back-to-Back\] students say 'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.' \[p48-49, independent writing\] students write and draw what they notice and wonder about the sun, moon, and stars.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| acquire academic/specialized vocabulary through grade-level texts and content | met | student | students discuss the sun as it appears in the read-aloud text ... Show the card for sun; students repeat the word with a gesture |
| apply that vocabulary to communicate | met | student | 'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.' |

**Evidence:** students discuss the sun as it appears in the read-aloud text ... Show the card for sun; students repeat the word with a gesture  |  'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.'  
**Why this label:** Swept across the whole lesson (p44-49), not the Word Wall snippet alone: students ACQUIRE the topic vocabulary through the grade-level text read aloud (p44) and the Word Wall (p45), and APPLY it in their own speaking ('I noticed that the sun...', p48) and writing (p48-49) \-\> both acquire and apply met \-\> full. The standard is an OR over general/academic/specialized vocabulary, so which bucket 'sun' falls in need not be resolved. Applies locked SME ruling R1 (a read-aloud counts as a grade-level text for (I) interpretation at K-1).

---

### `GA1-M2-001` — `1.P.CP.2.a` (I/C) → **FULL**  ·  *anchor\_full\_manner\_modifier*

**Standard:** Communicate clearly to present ideas, information, and texts.  
**Lesson:** Unit 1, Lesson 1, Opening B: Picture Tea Party — p. 45 · tier: **core**

> Once everyone has looked closely at their picture, you will signal them to share with their small group using the sentence frame 'In my picture, I see\_\_\_\_\_\_\_.' Group member A should share first.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| present ideas/information clearly (aloud) | met | student | share with their small group using the sentence frame 'In my picture, I see\_\_\_\_\_\_\_.' |

**Evidence:** share with their small group using the sentence frame 'In my picture, I see\_\_\_\_\_\_\_.'  
**Why this label:** Students present an observation aloud to their small group ('In my picture, I see \_\_\_'). Under the GA presentation manner-modifier fence, speaking aloud to communicate an idea satisfies both the act (present ideas) and the manner (clearly) \-\> full. The standard's 'ideas, information, and texts' is an interchangeable object-list (R2), so presenting an idea/observation satisfies it \-- 'texts' is not a separately-required component. Do not dock for the lesson never separately drilling volume.

---

### `GA1-M2-002` — `1.P.CP.2.a` (I/C) → **FULL**  ·  *full\_recurrence*

**Standard:** Communicate clearly to present ideas, information, and texts.  
**Lesson:** Unit 1, Lesson 1, Work Time B: Back-to-Back and Face-to-Face — p. 48 · tier: **core**

> Guide students through the protocol using the following question and sentence frame: 'What is one thing you noticed about the sun in the video?' / 'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.'

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| present ideas/information clearly (aloud) | met | student | 'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.' |

**Evidence:** 'I noticed that the sun \_\_\_\_\_\_\_\_\_\_.'  
**Why this label:** Second attested instance in the same lesson: the student states an observation aloud to a partner \-\> present-clearly met (manner-modifier fence) \-\> full. As in 001, 'ideas, information, and texts' is an interchangeable object-list (R2), so presenting an observation satisfies it. Included to show the standard recurs across the lesson (recall).

---

### `GA1-M2-009` — `1.P.EICC.4.c` (C) → **FULL**  ·  *anchor\_full*

**Standard:** Generate ideas for content by assessing prior knowledge, gathering information from texts, and engaging in discussions with others.  
**Lesson:** Unit 1, Lesson 1, Work Time C: Independent Writing — p. 48-49 · tier: **core**

> Now that they have shared what they noticed and wondered about the sun, moon, and stars with their classmates, they are going to write down and draw what they notice and wonder. Invite students to use the response sheet to capture the things they noticed and wondered ... using pictures and words.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| generate ideas for content (prior knowledge \+ info from texts/media \+ discussion) | met | student | Invite students to use the response sheet to capture the things they noticed and wondered |

**Evidence:** Invite students to use the response sheet to capture the things they noticed and wondered  
**Why this label:** Students generate their own content ideas (notices and wonders) after gathering information from the videos and engaging in discussions (tea party, Back-to-Back) \-- exactly the three sources 1.P.EICC.4.c names \-\> full. This is the (C) generate-ideas process step, NOT drafting a genre piece (see 1.P.EICC.4.e cases).

---

### `GA1-M2-005` — `1.T.RA.1.a` (I) → **FULL**  ·  *anchor\_full*

**Standard:** Ask questions about topics of interest for research.  
**Lesson:** Unit 1, Lesson 1, Work Time C: Independent Writing (Noticing & Wondering) — p. 48-49 · tier: **core**

> Direct students' attention to the second learning target: 'I can ask questions about what I notice in pictures and videos of the sun, moon, and stars.' Invite students to use the response sheet to capture the things they noticed and wondered ... Provide students with sentence frames as needed: 'I notice \_\_\_\_\_.' / 'I wonder \_\_\_\_\_\_\_\_\_\_\_.' (ELL note: point out that a question word usually follows the phrase I wonder; 'What are some question words you can use to write your wonder?')

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| ask questions about a topic of interest | met | student | 'I wonder \_\_\_\_\_\_\_\_\_\_\_.' |

**Evidence:** 'I wonder \_\_\_\_\_\_\_\_\_\_\_.'  
**Why this label:** Students generate their own questions ('wonders') about the sun/moon/stars \-- a topic of interest \-- and the curriculum explicitly frames wonders as questions using question words. Student performs the ask act on a topic of interest \-\> 1.T.RA.1.a full. (This is (I) research-questioning, distinct from 1.P.CP.2.d dialogue Q\&A.)

---

### `GA1-M2-014` — `1.T.T.4.b` (C) → **FULL**  ·  *anchor\_full\_construction*

**Standard:** Use poetic techniques to create poems using simple words and/or phrases that may or may not rhyme.  
**Lesson:** Unit 3, Lesson 5, Work Time B: Independent Writing ('What the Moon Sees' Poem, Verse 3\) — p. 391 · tier: **core**

> Display the 'What the Moon Sees' poem and read verses 1 and 2 aloud. Tell students that now they will write their own version of verse 3 and the closing independently. Answer clarifying questions and invite students to begin writing.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| create a poem using simple words/phrases (may or may not rhyme) | met | student | now they will write their own version of verse 3 and the closing independently |

**Evidence:** now they will write their own version of verse 3 and the closing independently  
**Why this label:** Students independently compose their own verse of a narrative poem \-\> the (C) create-a-poem act is performed by the student \-\> 1.T.T.4.b full. A genuine Construction example (the I/C axis's C side), grounded in independent \-- not shared \-- writing.

---

### `GA1-M2-020` — `1.L.V.3.a` (I) → **PARTIAL**  ·  *supplemental\_cap*

**Standard:** Use context within and beyond a sentence to determine or clarify the meaning of unknown and multiple-meaning words and phrases.  
**Lesson:** Unit 1, Lesson 6, Work Time A: 'For ELLs: Mini Language Dive' — p. 100 · tier: **supplemental**

> \[For ELLs: Mini Language Dive\] Point to and read aloud the chunk: 'Pa by the door,' and ask: ... 'What does the word by mean in this chunk?' (next to)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| use context to determine/clarify the meaning of unknown/multiple-meaning words | partially\_met | student | 'What does the word by mean in this chunk?' (next to) |

**Evidence:** 'What does the word by mean in this chunk?' (next to)  
**Why this label:** Two independent reasons this is partial, not full: (1) it occurs only in a 'For ELLs: Mini Language Dive' support box \-\> optional-tier cap per ruling R3; and (2) the standard names two target types ('unknown AND multiple-meaning words/phrases') and only one is addressed here \-- a still-open decomposition question, but moot since (1) already caps it. The student does perform the context-clue act \-\> not none.

---

### `GA1-M2-021` — `1.P.CP.1.c` (I/C) → **PARTIAL**  ·  *partial\_missing\_feedback\_and\_shared\_project*

**Standard:** Contribute to discussions and shared projects by offering ideas, listening to the ideas of others, and providing feedback.  
**Lesson:** Unit 1, Lesson 1, Opening B: Picture Tea Party (turn-taking) — p. 45 · tier: **core**

> Once everyone has looked closely, they share ... Group member A should share first. Once every group member has shared, they should raise their hands to show they have finished talking and listening.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| offer ideas | met | student | Group member A should share first |
| listen to the ideas of others | met | student | raise their hands to show they have finished talking and listening |
| provide feedback | not\_met | none | — |
| contribute to a shared project (not only a discussion) | not\_met | none | — |

**Evidence:** Group member A should share first  |  raise their hands to show they have finished talking and listening  
**Why this label:** The tea party is a discussion, so students offer ideas and listen (two of the three act-components met); the protocol has no step where students give each other feedback \-\> feedback absent. Separately, the standard names two collaborative contexts \-- 'discussions AND shared projects' \-- which are complementary (a sustained shared project is a distinct context from a discussion; R2-split), and only the discussion context occurs here, so the shared-projects context is unmet. Two gaps \-\> partial.

---

### `GA1-M2-003` — `1.P.CP.2.d` (I/C) → **PARTIAL**  ·  *boundary\_partial\_full\_ask\_absent*

**Standard:** Engage in dialogue with audiences by asking and answering questions.  
**Lesson:** Unit 1, Lesson 3, Work Time B: Close Read-aloud — p. 68 · tier: **core**

> Direct their attention to the posted learning target and read it aloud: 'I can ask and answer questions about the boy and the sun in Summer Sun Risin' using key details from the text.' Using a total participation technique, invite responses from group: 'What are key details?' ... 'What is the setting of a story?'

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| ask questions (student generates a question) | not\_met | teacher | *(teacher: 'What are key details?' ... 'What is the setting of a story?')* |
| answer questions (in dialogue) | met | student | invite responses from group: 'What are key details?' ... 'What is the setting of a story?' |

**Evidence:** invite responses from group: 'What are key details?' ... 'What is the setting of a story?'  
**Why this label:** The learning target claims 'ask and answer,' but the activity has the TEACHER pose every text-dependent question ('total participation technique, invite responses'); students only answer. Answer met, ask absent \-\> partial. This is the key over-crediting trap: a matcher keyed on the target's words would call it full. It is not.

---

### `GA1-M2-004` — `1.P.CP.2.d` (I/C) → **PARTIAL**  ·  *boundary\_partial\_full\_ask\_absent*

**Standard:** Engage in dialogue with audiences by asking and answering questions.  
**Lesson:** Unit 1, Lesson 1, Opening A: Reading Aloud 'Elvin' — p. 44 · tier: **core**

> Using a total participation technique, invite responses from the group: 'What does Elvin observe about the sun?' ... 'What does Elvin wonder about the moon?'

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| ask questions (student generates a question) | not\_met | teacher | *(teacher: 'What does Elvin observe about the sun?' ... 'What does Elvin wonder about the moon?')* |
| answer questions (in dialogue) | met | student | invite responses from the group: 'What does Elvin observe about the sun?' |

**Evidence:** invite responses from the group: 'What does Elvin observe about the sun?'  
**Why this label:** Same pattern: teacher-posed questions, students answer. Answer met, ask absent \-\> partial. Note (recall finding): across Lessons 1 and 3 the unit never scripts students generating their own questions in dialogue, so 1.P.CP.2.d is never fully met here \-- a real gap worth surfacing.

---

### `GA1-M2-007` — `1.P.EICC.3.e` (I) → **PARTIAL**  ·  *one\_of\_two\_ops\_make\_only*

**Standard:** Make and track predictions about the events and information likely to come next.  
**Lesson:** Unit 1, Lesson 1, Opening A: Reading Aloud 'Elvin' — p. 44 · tier: **core**

> Using a total participation technique, invite responses from the group: 'Based on the title of the story, what do you think this story will be about?' (a little boy who likes things in the sky; ...)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| make a prediction | met | student | 'Based on the title of the story, what do you think this story will be about?' |
| track the prediction (revisit/confirm as reading proceeds) | not\_met | none | — |

**Evidence:** 'Based on the title of the story, what do you think this story will be about?'  
**Why this label:** Students make a prediction from the title (make met). The substandard is make AND track predictions; nothing has students revisit or confirm the prediction as the text unfolds \-\> track absent \-\> partial (make-only).

---

### `GA1-M2-008` — `1.P.EICC.3.e` (I) → **PARTIAL**  ·  *one\_of\_two\_ops\_make\_only*

**Standard:** Make and track predictions about the events and information likely to come next.  
**Lesson:** Unit 1, Lesson 6, Work Time A: Close Read-aloud Session 4 (CORE turn-and-talk, predicting the ending) — p. 99 · tier: **core**

> \[Work Time A, core\] Invite students to turn and talk to an elbow partner: 'What time of day do you think the end of the story takes place?' ... 'Where do you think the sun will be at the end of the story?' (Distinct from the later 'Meeting Students' Needs / MMR' support box, which revisits the same prediction as differentiation.)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| make a prediction | met | student | 'Where do you think the sun will be at the end of the story?' |
| track the prediction (revisit/confirm) | not\_met | none | — |

**Evidence:** 'Where do you think the sun will be at the end of the story?'  
**Why this label:** Scored on the CORE Work Time A turn-and-talk (every student predicts the ending) \-- NOT the supplemental MMR box a few lines later, which revisits the same prediction as differentiation. Make met; no step has students track/confirm the prediction as they then read the ending \-\> partial (make-only). (Had the MMR box been the source, R3 would also cap it at partial.)

---

### `GA1-M2-023` — `1.P.EICC.3.f` (I) → **PARTIAL**  ·  *partial\_infer\_make\_only\_supplemental*

**Standard:** Make, track, and support inferences about different levels of meaning within the text.  
**Lesson:** Unit 1, Lesson 6, Work Time A: 'For ELLs: Mini Language Dive' — p. 100 · tier: **supplemental**

> \[For ELLs: Mini Language Dive\] Ask: 'What does this verse mean?' (Responses will vary.) ... 'Now what do you think the verse means?'

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| make an inference about meaning | partially\_met | student | 'Now what do you think the verse means?' |
| track/support the inference across levels of meaning (with evidence) | not\_met | none | — |

**Evidence:** 'Now what do you think the verse means?'  
**Why this label:** Students infer what the verse means (make), but are not asked to support with evidence or track across levels \-\> partial on the make/track/support decomposition. It is also a 'For ELLs: Mini Language Dive' support box, so the make act is optional-tier (capped) per ruling R3. Comprehension is genre-neutral in GA, so genre is not a factor.

---

### `GA1-M2-019` — `1.P.EICC.3.g` (I) → **PARTIAL**  ·  *supplemental\_cap*

**Standard:** Determine the meanings of unfamiliar words and concepts by applying knowledge of context and of academic vocabulary and word parts.  
**Lesson:** Unit 1, Lesson 6, Work Time A: 'For ELLs: Mini Language Dive' — p. 100 · tier: **supplemental**

> \[For ELLs: Mini Language Dive\] Point to and read aloud the chunks: 'stars overhead.' ... 'What two words do you see in overhead? What do you think overhead means?'

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| determine meaning of an unfamiliar word by applying knowledge of word parts | partially\_met | student | 'What two words do you see in overhead? What do you think overhead means?' |

**Evidence:** 'What two words do you see in overhead? What do you think overhead means?'  
**Why this label:** Students genuinely perform the word-parts strategy on 'overhead' (over \+ head) \-\> not none. But the activity is a 'For ELLs: Mini Language Dive' support box \-- optional/differentiation-tier, not core instruction \-\> capped at partial per ruling R3.

---

### `GA1-M2-006` — `1.T.RA.1.a` (I) → **PARTIAL**  ·  *partial\_optional\_act*

**Standard:** Ask questions about topics of interest for research.  
**Lesson:** Unit 1, Lesson 1, Opening B: Picture Tea Party (protocol step 6\) — p. 45 · tier: **core**

> Tell students that this time, they will share a prediction about what they might learn OR a question about their picture, using a sentence frame. Group member A should share first.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| ask questions about a topic of interest | partially\_met | student | they will share a prediction about what they might learn or a question about their picture |

**Evidence:** they will share a prediction about what they might learn or a question about their picture  
**Why this label:** The directive offers a choice \-- 'a prediction OR a question' \-- so a given student may predict rather than ask; the ask act is not guaranteed. Under the engine's optional-act rule, an act the student may or may not perform caps at partial, not full. (005 carries the clean full for 1.T.RA.1.a, where every student writes wonders.) Verbatim location confirmed: Lesson 1, Opening B, Picture Tea Party protocol step 6, EL p.45.

---

### `GA1-M2-018` — `1.T.RA.2.a` (I) → **PARTIAL**  ·  *supplemental\_cap*

**Standard:** Refer to parts of texts when supporting an idea, answer, or opinion.  
**Lesson:** Unit 1, Lesson 6, Work Time A: 'For ELLs: Mini Language Dive' — p. 100 · tier: **supplemental**

> \[For ELLs: Mini Language Dive\] Point to and read aloud the chunk: 'Pa by the door,' and ask: 'What is Pa doing?' (Pa is playing guitar and singing by the door.)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| refer to a part of the text when supporting an answer | partially\_met | student | 'What is Pa doing?' (Pa is playing guitar and singing by the door.) |

**Evidence:** 'What is Pa doing?' (Pa is playing guitar and singing by the door.)  
**Why this label:** The student's answer is anchored to the text chunk 'Pa by the door', so the refer-to-text act is genuinely performed \-\> not none. But it occurs only inside a 'For ELLs: Mini Language Dive' support box \-- optional/differentiation-tier instruction, not the core lesson \-\> capped at partial per ruling R3. (This also resolves the earlier teacher-surfaced-text flag: it lands at partial either way.)

---

### `GA1-M2-024` — `1.T.SS.2.a` (I) → **PARTIAL**  ·  *partial\_identify\_only\_supplemental*

**Standard:** Identify and explain the use of descriptive words in texts.  
**Lesson:** Unit 1, Lesson 3, 'For ELLs' support: Descriptive Words in the Song — p. 67 · tier: **supplemental**

> \[For ELLs\] Reread the lyrics aloud and invite students to listen carefully for words that describe the sun and to give a silent signal when they hear one. Invite students to underline the words that they identify.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| identify descriptive words in the text | partially\_met | student | underline the words that they identify |
| explain the use of the descriptive words | not\_met | none | — |

**Evidence:** underline the words that they identify  
**Why this label:** Students identify descriptive words (underline words that describe the sun); the explain-the-use component is absent \-\> partial on the components. It is also a 'For ELLs' support note, so the identify act is optional-tier (capped) per ruling R3.

---

### `GA1-M2-012` — `1.T.T.1.a` (I) → **PARTIAL**  ·  *partial\_two\_of\_four\_components*

**Standard:** Identify techniques used to craft stories, including characters, setting, major events, and dialogue.  
**Lesson:** Unit 1, Lesson 3, Closing A: Character & Setting — p. 70 · tier: **core**

> Invite students to turn and talk to an elbow partner: 'Who is the main character?' (the boy) 'Where does the story take place?' (a farm). ... writing and drawing about the main character and setting using key details from the text.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| identify characters | met | student | 'Who is the main character?' (the boy) |
| identify setting | met | student | 'Where does the story take place?' (a farm) |
| identify major events | not\_met | none | — |
| identify dialogue | not\_met | none | — |

**Evidence:** 'Who is the main character?' (the boy)  |  'Where does the story take place?' (a farm)  
**Why this label:** Students identify character and setting (two of the four components 1.T.T.1.a names); major events and dialogue are not addressed here \-\> partial. This is an (I) identify act \-- keep it distinct from the (C) create substandard (see 015).

---

### `GA1-M2-013` — `1.T.T.1.a` (I) → **PARTIAL**  ·  *partial\_one\_of\_four\_components*

**Standard:** Identify techniques used to craft stories, including characters, setting, major events, and dialogue.  
**Lesson:** Unit 1, Lesson 6, Work Time B: Role-Playing the Ending Events — p. 101-103 · tier: **core**

> Move students into pre-determined pairs ... they are going to use the Role-Play protocol to act out a few of the ending events of Summer Sun Risin'. ... 'What does the boy experience when the sun is setting?' (The boy is reading a book ...)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| identify major events | met | student | act out a few of the ending events of Summer Sun Risin' |
| identify characters | not\_met | none | — |
| identify setting | not\_met | none | — |
| identify dialogue | not\_met | none | — |

**Evidence:** act out a few of the ending events of Summer Sun Risin'  
**Why this label:** Students identify/enact the major ending events (major-events component met); character, setting, and dialogue are not the object here \-\> partial. With 012, the unit covers 1.T.T.1.a's components across lessons \-- apply the Step 6 shared-activity consistency check when the same lesson is scored against paired standards.

---

### `GA1-M2-022` — `1.T.T.1.c` (I) → **PARTIAL**  ·  *partial\_describe\_only\_supplemental*

**Standard:** Describe traits of the main characters and explain how their words and actions support the central message, lesson, or moral of the story.  
**Lesson:** Unit 1, Lesson 6, Work Time A: 'For ELLs: Mini Language Dive' — p. 100 · tier: **supplemental**

> \[For ELLs: Mini Language Dive\] Point to and read aloud the chunk: 'me tucked in bed' and ask: 'What is the boy doing?' (sleeping; lying in bed)

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| describe traits/actions of the main character | partially\_met | student | 'What is the boy doing?' (sleeping; lying in bed) |
| explain how the character's words/actions support the central message/lesson/moral | not\_met | none | — |

**Evidence:** 'What is the boy doing?' (sleeping; lying in bed)  
**Why this label:** Students describe the character's action (the boy is sleeping); the explain-the-central-message component is absent \-\> partial on the components. It is also a 'For ELLs: Mini Language Dive' support box, so the describe act is optional-tier (capped) per ruling R3 \-- partial for both reasons.

---

### `GA1-M2-017` — `1.L.V.1.b` (C) → **NONE**  ·  *known\_negative\_acquire\_only\_no\_use*

**Standard:** Use grade-level general, academic, and specialized vocabulary words and phrases to communicate in a variety of settings.  
**Lesson:** Unit 1, Lesson 3, Work Time B: teacher-supplied definition of 'risin'' — p. 68 · tier: **core**

> Briefly review the definition of risin' (rising) (to climb upwards). \[No activity in the lesson has students use the word 'risin'' to communicate their own meaning; the word otherwise appears only as a fixed lyric students sing.\]

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| use grade-level vocabulary to communicate in a variety of settings | not\_met | teacher | *(teacher: Briefly review the definition of risin' (rising) (to climb upwards).)* |

**Evidence:** *(empty — none)*  
**Why this label:** Clean acquire-only known-negative for the (C) use substandard: the TEACHER supplies the meaning of 'risin'' and no activity has the student use the word to communicate their own meaning \-\> none. Swept the lesson: students later sing the scripted lyric 'summer sun's a-risin'', but reciting a fixed lyric is not the student selecting and using the word to communicate \-\> reciting is not using. Replaces the earlier Word-Wall none, which was unsafe: that lesson DOES have students apply the words (see 016).

---

### `GA1-M2-010` — `1.P.EICC.4.e` (C) → **NONE**  ·  *known\_negative\_actor\_gate*

**Standard:** Construct an initial draft by integrating ideas and information; selecting words, phrases, and sentences; and incorporating craft techniques that will best achieve the purpose of the text and resonate with the target audience.  
**Lesson:** Unit 1, Lesson 1, Closing A: Shared Writing — p. 49 · tier: **core**

> Using a total participation technique, invite responses from the group: 'What did you notice about the sky, the sun, the moon, or the stars?' As students share out, capture and clarify their responses on the Noticing and Wondering anchor chart.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| construct an initial draft (student integrates ideas into a draft) | not\_met | teacher | *(teacher: As students share out, capture and clarify their responses on the ... anchor chart)* |

**Evidence:** *(empty — none)*  
**Why this label:** Shared/interactive writing: students contribute ideas orally but the TEACHER scribes the draft onto the anchor chart. The drafting act is the teacher's \-\> student-quote gate fails \-\> none (actor gate). (Students may instead meet 1.P.EICC.4.c generate-ideas \-- see 009.) Known-negative measuring over-crediting on writing-process standards.

---

### `GA1-M2-011` — `1.P.EICC.4.e` (C) → **NONE**  ·  *known\_negative\_artifact\_gate*

**Standard:** Construct an initial draft by integrating ideas and information; selecting words, phrases, and sentences; and incorporating craft techniques that will best achieve the purpose of the text and resonate with the target audience.  
**Lesson:** Unit 1, Lesson 3, Closing A: Independent Writing (Response Sheet Part 1\) — p. 70 · tier: **core**

> Point to Part 1 and read the title aloud: 'Use words and pictures to answer these questions.' Point to the table and read the headings: 'Who are the main characters?' 'Where does the story take place?' Today they will answer these two questions using pictures and words.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| construct an initial draft (student integrates ideas into a draft) | not\_met | student | *(teacher: answer these two questions using pictures and words)* |

**Evidence:** *(empty — none)*  
**Why this label:** Even though the STUDENT now holds the pencil, completing two scaffolded response-sheet cells ('Who are the main characters? / Where does the story take place?') is not 'constructing an initial draft by integrating ideas and information' \-\> none (artifact gate). Distinct from 010: here the actor is the student but the artifact isn't draft-like. Both gates stand alone.

---

### `GA1-M2-015` — `1.T.T.1.e` (C) → **NONE**  ·  *known\_negative\_ic\_mode\_mismatch*

**Standard:** Use knowledge of narrative techniques (e.g., characters, settings, events) to create texts that share real or imagined experiences and events with a sense of closure.  
**Lesson:** Unit 1, Lesson 3, Closing A: Character & Setting (same activity as 012\) — p. 70 · tier: **core**

> Invite students to turn and talk: 'Who is the main character?' (the boy) 'Where does the story take place?' (a farm). ... writing and drawing about the main character and setting using key details from the text.

| clause | judgment | actor | evidence |
| :---- | :---- | :---- | :---- |
| use narrative techniques to CREATE a text sharing an experience with closure | not\_met | student | *(teacher: writing and drawing about the main character and setting)* |

**Evidence:** *(empty — none)*  
**Why this label:** The single most important GA-specific known-negative: this is an (I) 'identify the elements of the read text' activity. Scored against the (C) create substandard 1.T.T.1.e, the mode is wrong \-- identifying character/setting is not creating a narrative with closure \-\> none (I/C mode mismatch), NOT partial. Note this is the SAME activity that is partial for 1.T.T.1.a (012); the label differs because the mode differs.

---

