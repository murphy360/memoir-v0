# Memoir requirements

Owner direction, 2026-09-27: keep the idea, rewrite the software from the ground up. This document is what the
rewrite starts from. It was pulled out of the version 0 code, its docs and its history, then cleaned of the
accidents. Version 0 stays running at `https://dontpanic.ddns.net/memoir` behind Caddy's basic auth as a reference
and a stopgap.

How to read it:

- "Must" is a requirement for the first release. "Should" is expected but can slip. "May" is an option.
- "Decide:" marks a choice the owner has not made yet. Section 14 collects them.
- "v0" means the current code. Where a v0 number or rule is cited, the rewrite starts from it and may change it
  with a reason written down.
- Prose is short sentences, one idea each, no em-dashes.

## 1. Purpose and users

### 1.1 The idea

Memoir is a voice-first family memory archive for one household. A person tells a story, the system writes it down,
works out when and where it happened and who was there, files it on a life timeline, and asks a good follow-up
question so the next story goes deeper. Photos and documents attach to the events they show. Over time the timeline
becomes a biography with evidence.

### 1.2 Goals (from the v0 README, still valid)

1. Capture is effortless: one tap to record, on a phone, in under fifteen seconds.
2. Speech becomes accurate, searchable text.
3. The timeline is ordered by when things happened, not when they were recorded.
4. AI asks personal follow-up questions that draw out detail.
5. The family owns its data: private by default, exportable in full, deletable.

### 1.3 Users

| Persona | Who | Needs |
|---|---|---|
| **The storyteller** ("the grandmother") | An older, non-technical family member whose life is being recorded | One obvious button. Plain words. Confirmation that it worked and where it went. Never a dead end. |
| **The archivist** (the owner) | Sets the system up, curates the timeline, fixes dates and names, reviews faces | Power tools that stay out of the storyteller's way. Bulk operations. Confidence that nothing is silently lost. |
| **A contributor** | A child or grandchild who records the storyteller, uploads photos, adds context | Their own login. Their uploads attributed to them. The same simple capture. |
| **A viewer** (optional) | Family who browse and listen | Read-only access. Decide: whether viewers exist in version 1 (section 14). |

### 1.4 Fixed product constraints (from the v0 grandmother review skill)

- The hierarchy is Periods, then Events, then evidence. Epics and Threads refine it (section 3).
- Photos and documents are evidence attached to events by default, not standalone memories.
- The timeline supports a zoomed-out roll-up: minor items collapse, weighty ones stay.
- Manual linking comes before AI suggestion. AI proposes; a person confirms.

## 2. Lessons from version 0

Keep:

- The domain model. Periods, epics, events, threads, memories, assets, people, places, faces and questions all earned
  their place. Section 3 defines them cleanly.
- Free-text dates with a parsed sortable range behind them ("Summer 1968", "the 1960s", "1998 to 2002").
- "No key means the feature is off" for every external service, failing soft with an empty result and a visible
  notice, never a low-quality fallback (the OpenCV lesson).
- Quick Memory, the one-tap recording with technical choices hidden behind "Advanced".
- The photo pipeline stages: compress, EXIF and GPS, reverse geocode, faces, two-pass AI analysis with context.
- Self-hosted CompreFace for faces so biometric data stays home.
- The standards tooling from PR #1 (section 12).

Drop or redo:

- No accounts. The rewrite ships with logins (section 9).
- Everything synchronous inside the request. A period analysis could run for minutes in one HTTP call. Long work
  becomes jobs (section 12).
- Startup backfills that rewrite data on every boot and reverted manual edits (appendix C).
- SQLite with hand-written `ALTER TABLE` and foreign keys never enforced. Real migrations, enforced constraints.
- The legacy `memory` object living beside the `event` plus `asset` model, joined by `legacy_memory_id`. One model.
- Four different photo-processing paths with different orderings. One pipeline.
- Two files holding most of the app (`main.py` 3120 lines, `page.tsx` 3940 lines). Size limits are enforced from
  the first commit.
- Whole-dataset reload after every click, one global status string shown in a closed drawer, controls that only
  render when a card is open, and five other "the feature exists but nobody can see it" bugs (section 11.6).
- Hard-coded heuristics: a Pittsburgh school list for period titles, the "car" question, the "play" title rule,
  keyword emotional tone, regex people extraction.
- The persona review that stopped after one day. Section 11 turns its open requests into requirements.

## 3. Domain model

### 3.1 Entities

**Archive.** One family's memoir. Every other row belongs to exactly one archive (`archive_id`). Version 1 has one
archive per deployment; the column exists so a second household is a data change later. Holds the settings
(section 3.4).

**User.** A login (section 9). Every row that a person creates or changes records `created_by`, `created_at`,
`updated_by`, `updated_at`. Rows are soft-deleted (`deleted_at`) with an owner-only purge.

**Person.** Someone in the family's life. Fields: `name` (unique within the archive, case-insensitive), aliases (any
number, case-insensitive; one alias may point at several people, so "the kids" fans out), contact details (phone,
email, address, notes, birthday as free text), an optional link to the archive's own user account, and an optional
face identity (section 7). Derived, never stored: memory count, photo count, avatar (a recent confirmed face).

**Place.** A named location. `name` unique within the archive. Should carry optional coordinates so a photo's GPS,
an event's location and a place can meet. v0 kept three unlinked free-text location fields; the rewrite links them.

**Period.** A chapter of life ("Childhood", "Navy years"). Title, free-text start and end, parsed sortable start and
end, summary (typed or generated, with a flag saying which). Slug for stable URLs.

**Epic.** An arc inside one period ("Building the house"). Belongs to exactly one period. Title, description, weight
1 to 10, free-text dates with parsed range, optional thread.

**Event.** A moment or episode. The unit that evidence attaches to. Belongs to at most one period and at most one
epic; the epic decides the period. Title, description, weight 1 to 10, free-text date with parsed start and end and
a precision (day, month, year, decade, approximate, unknown), location text and optional Place, optional thread,
generated summary, research results, a pending suggested edit (section 6.6), and the analysis state (section 6.8).

**Thread.** A theme across time ("Faith", "The farm", "Grandpa Joe"). Title unique in the archive, slug, summary.
Tags epics and events, never periods (v0 tried periods and moved off it). Deleting a thread untags; it deletes
nothing.

**Memory.** One told story: the narration. A memory has a transcript (or typed text), a title, a description, the
storyteller (a Person), the account that uploaded it, the recording date, the story's own free-text date with parsed
range and precision, emotional tone, the people and places mentioned (links to Person and Place), an optional
response-to-question link, research results, and zero or one audio blob. A memory belongs to exactly one event once
placed. Until placed it sits in the inbox (section 5.4). v0's "document memory" becomes an asset with extracted text
plus, optionally, a memory about it.

**Asset.** A file: photo, document or audio. Kind, title, notes, blob (section 12), original filename, content type,
size, SHA-256 (used for duplicate detection this time), extracted text or AI excerpt, capture time as free text plus
parsed start and end, GPS, place names (from EXIF, from reverse geocoding, from AI analysis) and a resolved Place,
camera fields, dimensions, orientation, raw EXIF. An asset links to any number of events with a relation type
(`evidence`, `recording`). Unlinked assets sit in the inbox. A photo's narrations (memories recorded about it) are
visible from the photo.

**Face.** One detected face in one photo. Normalised bounding box, detector confidence, the recognised identity
candidate and its similarity, plugin outputs (age range, gender) if enabled, the raw recogniser result, and the
confirmed Person if a human confirmed or the system auto-assigned above the threshold. Records whether the assignment
was manual or automatic. A face may belong to an unknown-face cluster (section 7.4).

**Question.** A follow-up prompt. Text, status (pending, answered, dismissed), the memory or event it came from, the
memory that answered it, scope (general, period, event, person). Unique by normalised text among pending questions.

**Job.** A unit of background work (section 12): type, target, status, progress, result, error, requested by,
timestamps.

### 3.2 Relationships and rules

- Period 1:N Epic (required parent). Period 1:N Event (optional). Epic 1:N Event (optional).
- An event with an epic takes the epic's period. Moving an epic moves its events. Deleting an epic detaches its
  events to the period. Deleting a period asks what to do with its epics and events: move them to another period or
  unassign them. Nothing is deleted silently.
- Thread 1:N Epic, Thread 1:N Event, optional both ways.
- Event 1:N Memory. Event N:M Asset with a relation type. A memory may reference assets it is about (its photo).
- Memory N:M Person (mentioned), Memory N:1 Person (storyteller). Memory N:M Place.
- Asset 1:N Face. Face N:1 Person (optional). Person 1:1 face identity (the recogniser subject).
- Merging two events moves memories, assets and faces to the target and fills the target's empty fields from the
  source. Merging two periods moves epics too (v0 lost them). Merging two people moves everything and reconciles the
  face identities (section 7.3).
- Every foreign key is enforced by the database. Every delete rule is explicit and tested.

### 3.3 Dates

One rule set for every free-text date (period, epic, event, memory, asset capture, birthday). Parsing must accept,
in this order of preference:

1. ISO dates and datetimes, a single day.
2. Explicit formats: `1968-07-16`, `7/16/1968`, `Jul 16, 1968`, `16 July 1968`, with or without ordinal suffixes.
   `July 1968` is the whole month.
3. Day ranges inside a month or across months: `July 16 to 18, 1968`, `July 16 to August 2, 1968`.
4. Year ranges with `-`, `to`, `through`, `until`, en dash or em dash: `1998 to 2002`.
5. Seasons: spring is March to May, summer June to August, fall or autumn September to November, winter December to
   the end of the following February.
6. Decades: `the 1960s`, first day to last day.
7. A bare year anywhere in the text: the whole year.

Years 1850 to 2099 (v0 stopped at 1900; the rewrite should accept a great-grandparent's birth). Anything else parses
to nothing, and the UI says so before saving. The parse result is stored as start and end dates plus a precision, and
sorting uses them: undated items sort last. A manually edited date is never overwritten by a background process.

### 3.4 Settings

Per archive: the storyteller's display name (v0's "main character name", editable any time), the archive's time zone,
which AI features are enabled, the auto-assign similarity threshold, and the face-detection-on-upload switch. Secrets
(API keys) are environment, not settings.

## 4. Capture

### 4.1 Recording

- The home screen has one primary action, **Record**. One tap starts recording. No device picker, no form. Stop is
  always visible while recording, on every screen that can record.
- Recording works in a mobile browser (MediaRecorder) and on the desktop. The input device, a level meter and a
  microphone test live under **Advanced**. The chosen device is remembered on that device.
- While recording: elapsed time and a live level meter. After stopping: an immediate playback of what was recorded,
  its length and size, then a clear status: uploading, processing, saved, or failed with a retry.
- Cancel discards without uploading and says so.
- A recording can start from: the home screen (goes to the inbox or the suggested event), an event ("add a memory to
  this event"), a period ("quick memory in this period"), a photo ("tell the story of this photo"), a person ("a
  memory about this person"), or a question ("answer this"). The context is shown while recording.
- Upload is resilient: chunked or resumable for long recordings, and a failed upload keeps the audio in the browser
  until it succeeds or the user discards it.
- Audio is normalised server-side to mono MP3 at 44.1 kHz, 128 kbps (v0's ffmpeg settings). If conversion fails the
  original is kept and transcription still runs. The original is kept alongside for a configurable time (default 30
  days) then purged, or kept forever if the setting says so.

### 4.2 Typed memories

- A memory can be typed instead of spoken, with an optional date. It goes through the same analysis minus
  transcription.

### 4.3 Photos and documents

- **Add photos** is its own primary action, next to Record. It accepts many files at once, from the picker, by drag
  and drop, from the clipboard, and by sharing from a phone (web share target where supported).
- Accepted: JPEG, PNG, GIF, WebP, HEIC (converted to JPEG), PDF, plain text. Anything else is refused before upload
  with a plain message.
- Each file shows its own progress and outcome. One failure does not stop the others. Duplicates (same SHA-256 in
  the archive) are detected and offered as "already here, open it".
- A photo can be added to an event, a period or nothing (the inbox). Adding to a period without an event is allowed
  (v0 could not).
- An optional capture-date override applies to every file in the batch, and is honoured on every upload path.
- Photos are stored compressed for display: longest edge 2048, JPEG quality 85, EXIF preserved, and the original
  bytes kept as a separate blob. Documents are never altered.
- Processing after upload (EXIF, geocoding, faces, AI) is a background job with visible per-file, per-stage progress
  (section 6.7). The upload itself returns as soon as the file is safe.

## 5. Organising the timeline

### 5.1 Structure

- Periods sort by start date, undated last. Within a period, epics and events sort by start date, undated last.
- The user can create, rename, describe, date, re-date, weight, move, merge and delete periods, epics, events and
  threads, and edit every field that exists on them (v0 exposed only some).
- Weight 1 to 10 drives the zoomed-out view: at the widest zoom only weight 8 and above show, and a period card shows
  counts of what is hidden.
- Threads have a view of their own: a filtered timeline of everything tagged with the thread, across periods.

### 5.2 Editing

- Inline edit on every title, date and description: click to edit, Enter saves, Escape cancels, always with visible
  Save and Cancel. Saves are optimistic with an undo toast; failures roll back and say why.
- Selects apply on change, or need a button, but not a mix. Pick one and keep it.
- Every destructive action confirms in plain words that say what happens to the children ("its 12 events move to
  the period"). Every delete is soft and undoable from a trash view for 30 days.

### 5.3 Placing a memory

After a recording is saved the user sees, in plain words, where it went: "Saved to 1960s, Summer job" with one tap
to change it. The placement step offers:

1. The system's suggestion (section 6.4) as the first option.
2. Recent and nearby events, then periods.
3. "Somewhere new": create an event, or an epic, or a period right there, prefilled with the memory's date.

Suggested decade shortcuts ("the 1960s") make dating easy for the storyteller.

### 5.4 The inbox

Called **Waiting to be placed**, not "Unlinked Assets Inbox". Holds memories and assets that have no event. Each
item shows what it is, when it was captured, the suggested destination, and a one-tap **Place** that opens the
placement step. An item can be placed on an event or a period, or a new one made inline. An "Add your story" prompt
sits on any photo without a narration.

## 6. AI processing

### 6.1 General

- Every AI call goes through a provider interface. Gemini is the first provider (`gemini-2.5-flash` default, with
  per-task model overrides for research and photo analysis, as v0 had). Prompts, parsing and limits live in the
  service that owns the task, not in the provider adapter.
- Every AI task is a job (section 12) with a timeout, a retry policy, a cost record (model, tokens, duration) and a
  result stored with provenance: which model, which prompt version, when.
- The output of an AI task is a proposal until the storyteller or archivist accepts it, except for the transcript,
  the extracted metadata used for the initial placement suggestion, and photo excerpts, which apply directly but stay
  editable and marked as machine-generated.
- No API key: the feature is off, the UI says "AI is off" where the feature would appear, and nothing fails.
- Payload limits are respected: audio and photos are chunked or batched so one request never exceeds the provider's
  inline limit (v0 sent everything inline in one call). API keys travel in headers, never in URLs.
- Third-party calls are rate limited and cached where the provider asks for it (Nominatim: one request per second,
  results cached by coordinates rounded to three decimals).

### 6.2 Transcription

- Input: the normalised audio. Output: plain transcript text, stored on the memory, editable.
- Failure: the memory is saved with the audio, marked "transcription failed", with a retry. The storyteller is told
  the recording is safe.
- Should: speaker labelling when two people talk, and a confidence signal that the UI uses to invite a proofread.

### 6.3 Metadata extraction

From the transcript, by structured (function-call) output, one call:

- When it happened: date text, precision (day, month, year, decade, approximate, unknown), and the numeric parts.
- Who told it (the storyteller's name if they say it), who is mentioned, where it happened. Names are trimmed,
  capped and de-duplicated case-insensitively, then resolved against people and places, aliases included.
- A short title (4 to 10 words) and a one-paragraph description. v0's "Name's narration of this memory" title is
  gone.
- Emotional tone from a fixed list (positive, negative, reflective, neutral, mixed), by the model, not keywords.

If extraction fails the memory is saved with what exists and flagged "needs details" in the inbox. No regex fallback.

### 6.4 Placement suggestion

Given the memory's date range, people and places, suggest the event: the closest event by date in the matching
period, higher weight winning ties (v0's rule), then the period alone, then "new". The suggestion is shown, never
applied without confirmation, except for the storyteller's quick capture where the setting "file quick memories
automatically" is on. Auto-created events and periods are labelled as such and are ordinary rows afterwards, never
re-created by a background process.

### 6.5 Follow-up questions

- After each new memory, generate two to three questions that probe feeling, significance, people and themes, from
  the transcript with the storyteller, date, people and places as context. Never the fixed heuristics of v0.
- Questions are de-duplicated against every pending question by normalised text at write time, not read time.
- A question is scoped to the memory's event, its period, a person, or general. The UI shows it in that scope and
  in one "Questions for you" list.
- Answering: the storyteller taps the question and records. The new memory links to the question and inherits its
  scope as the placement suggestion. The question becomes answered. Dismiss hides it for good.
- Seed questions exist for an empty archive ("What should we call you", "Where and when were you born", "Tell me
  about your parents").

### 6.6 Summaries, research and suggested edits

- **Event summary.** From the event's memories and assets: two to four short paragraphs and three to six highlights.
  Regenerated on request and when a job notes the inputs changed (an input hash, as v0 had). Never overwrites a
  typed summary; typed and generated are stored separately and the UI shows which is which.
- **Period biography.** Third person, chronological, from the period's events. Same rules as the event summary.
- **Research.** On request, for a memory or an event: web-grounded research in four parts (what this likely meant,
  the bigger picture, related developments, questions worth exploring), with the search queries and up to eight
  sources kept. Research is a proposal panel with a date suggestion and an edit suggestion (title, date, description,
  with reasoning); each has Accept and Dismiss. Accepting a date suggestion updates the linked event too (v0 did not
  until restart). Research questions join the question list through the same de-duplication.
- **Period analysis.** On request: coverage of the period's dates against its events, recommended dates, title
  candidates from the event titles, and a biography. Presented as proposals with one "apply all" and per-item
  accepts. Title candidates come from the content, never from a hard-coded list. The counts of what ran are shown.

### 6.7 Photo analysis

One pipeline, one order, for every photo, whatever triggered it:

1. **EXIF.** Dimensions, camera, lens, orientation, capture time (with offset handling to UTC), GPS, EXIF place
   name. Raw EXIF kept. Runs once at upload; a manual capture-date override is never overwritten by re-runs.
2. **Reverse geocoding** when GPS exists and no place name yet. Name is "locality, region, country". Resolves to a
   Place when one is within a configurable distance.
3. **Faces** (section 7). Runs when the archive setting says so; can be run by hand.
4. **AI analysis**, two passes, batched with a batch size that respects the payload limit:
   - Pass 1, research: identify what is visible (signs, vehicles, uniforms, landmarks) and what was happening at that
     time and place, web-grounded, five to twelve sentences of notes.
   - Pass 2, structured: summary, suggested title (4 to 8 words), assessed place, visual evidence, contextual
     narrative, discrepancy flag between metadata and evidence. Context passed in: capture time, coordinates, known
     people from confirmed faces, the linked event, period and memory. Pass 1 failing is not fatal to pass 2.
   The excerpt and assessed place apply to the asset; the suggested title is a proposal unless the asset has no title.

Progress streams to the browser per photo and per stage (running, done, skipped, failed) over SSE or job polling,
survives a page reload, and is visible on the event, in the inbox and on the job list. "Processed" means the AI
excerpt exists; re-runs skip processed photos unless asked.

### 6.8 Analysis state

Events and periods record when they were last analysed and a hash of the inputs, so "what changed since" is cheap and
the UI can show "up to date" or "has new material".

## 7. People, places and faces

### 7.1 Directory

- People and places each have a list with search (name or alias), sort (most memories, most photos, A to Z), avatar,
  alias chips, and counts.
- A person has a page: contact details, identity (rename, aliases, merge, split, face identity), their memories,
  events and photos, a quick typed memory, and a face review queue (section 7.4). All identity actions are reachable
  from the page and from the list.
- A place has a page too: its memories, events and photos, and a map if it has coordinates. Places can be renamed,
  merged and given aliases (v0 had none of these).
- Rename keeps every link and renames the face identity in the recogniser in the same transaction.
- Merge moves aliases, mentions, storyteller roles and faces to the target; the source name becomes an alias.
- Split creates the new people, copies the mentions to each, keeps the old name as an alias if asked, and puts the
  source's faces in the review queue rather than dropping them.
- Delete asks what to do with faces and mentions, then soft-deletes.

### 7.2 Face detection and recognition

- Provider: self-hosted CompreFace behind a provider interface, one recognition service per archive. No fallback
  detector.
- Per photo: detect and recognise in one call (limit 50 faces, prediction count 3, detection probability threshold
  0.75, optional age and gender plugins). Store normalised boxes and the raw result.
- De-duplication: drop overlapping boxes (IoU over 0.42, larger box wins); one photo assigns a given identity to at
  most one face.
- Recognition below the minimum similarity (default 0.90) is treated as unknown.
- **Auto-assign** to a Person at or above the auto-assign threshold (default 0.92) when the identity resolves to
  exactly one person. Auto-assigned faces are marked automatic and appear in a review queue. Confirmed and manually
  assigned faces are never changed by a re-run; a re-run only adds and updates unconfirmed faces (v0 deleted and
  recreated them all).
- A face can be assigned, reassigned, cleared, confirmed, or discarded ("not a face") from the photo, the event and
  the person page.

### 7.3 Identity integrity

- A Person has at most one recogniser identity and an identity belongs to at most one Person, enforced by the
  database and by the service.
- Assigning a face to a person with no identity creates the identity named by a stable id (not the display name),
  enrols the face crop, and stores the id. Confirming a face enrols it. Renaming a person renames nothing in the
  recogniser because the identity is the id.
- Merge: if both people have identities, the source's faces are re-enrolled into the target's identity and the source
  identity is deleted, in a job with a record of what moved.
- Every recogniser mutation is logged and reversible from the archive's own data (the archive is the source of
  truth; the recogniser can be rebuilt from confirmed faces with one command).

### 7.4 Unknown people

- Unrecognised faces are clustered by embedding or by the recogniser's own subject for unknowns, not by exact image
  hash (v0's clusters never matched).
- A **People to name** screen shows clusters ordered by size, each with sample crops. From it: name the cluster
  (creates or picks a person and assigns every face), merge clusters, split a cluster, or dismiss faces. Approving
  a cluster enrols its best faces.
- A person page shows suggested faces for that person (recognised but unconfirmed) with approve and reject.

## 8. Questions and prompts

Covered in 6.5. Additional requirements:

- A "Questions for you" list is the storyteller's home when they open the app with nothing in mind: one question,
  one Record button.
- Should: a scheduled nudge (email or push, opt-in) with one question a week.

## 9. Accounts and access

v0 has no login of its own; Caddy's basic auth in front of `/memoir` is a stopgap. The rewrite ships with accounts
before it goes live.

### 9.1 Must have before live

- **A login.** Every page and every API route requires a signed-in user. There is no anonymous read.
- **Named users with passwords.** Email (or username) plus password, hashed with argon2id (bcrypt acceptable).
  Minimum length 12, no composition rules, checked against a breached-password list if cheap to do.
- **Sessions.** Server-side sessions in an HttpOnly, Secure, SameSite=Lax cookie. Idle timeout 30 days on a trusted
  device, sign out everywhere from the profile page. No tokens in local storage.
- **Owner bootstrap.** The first account is created from the command line or a one-time setup page that disappears
  afterwards. No open sign-up: the owner invites people by link (expires in 7 days, single use).
- **Rate limiting** on the login endpoint (per account and per IP) and a generic failure message.
- **Password reset** by the owner (set a temporary password that must be changed at next login). Email-based reset
  is optional and comes later.
- **The API accepts the session cookie only.** Media (audio, photos, thumbnails) is served through authenticated
  routes, never from a public static directory. Signed short-lived URLs are acceptable for `<img>` and `<audio>`.
- **CSRF protection** on state-changing requests (same-site cookie plus an origin check or a token).
- **Audit.** Who created and changed what, when, on every row (section 3.1), and a log of logins, invitations and
  role changes.

### 9.2 User control (roles)

A memoir is a shared family archive, so the unit of sharing is the archive, not the user.

| Role | Can |
|---|---|
| Owner | Everything, plus manage users, invitations, settings, API keys, export and delete the archive |
| Contributor | Record, upload, edit and organise memories, people, places and events; answer questions; review faces |
| Viewer | Browse and listen; nothing changes |

- One archive per deployment to start. Keep `archive_id` on every table so a second household later is a data
  change, not a rewrite.
- A recording has a storyteller (the Person speaking) and an uploader (the account). These differ when a grandchild
  records a grandparent. Both are shown.
- Deletions are soft with an owner-only purge, so a viewer's mistake or an over-eager auto-merge is recoverable.
- Should: a per-memory `visibility` (archive, or only me) from day one, even if the UI for it comes later.

### 9.3 Decisions for the owner

- Email plus password only, or also passkeys (WebAuthn)? Passkeys suit a storyteller who forgets passwords.
- Do viewers exist in version 1, or is everyone a contributor?
- Per-memory privacy in version 1 or later?

## 10. Privacy and data ownership

- Data at rest lives on the owner's server. Blobs and database are on an encrypted volume, or the application
  encrypts blobs with a key from the environment. Decide: which (section 14).
- Transcripts, photos and documents go only to the configured providers, and only when the archive has that feature
  on. A per-archive switch turns each provider off. The settings page names every provider that receives data.
- Faces never leave the host: CompreFace is self-hosted. No cloud face API is ever added as a fallback.
- Logs hold ids, durations and error classes. Never transcripts, never file contents, never keys.
- **Export** is first class from version 1: a ZIP with a JSON of every entity and every blob under stable names, and
  a human-readable HTML timeline, requested from the settings page and produced as a job. Should: PDF later.
- **Delete the archive** is available to the owner and removes everything, including recogniser identities.
- Retention: soft-deleted rows purge after 30 days; original (unnormalised) audio per the setting in 4.1.

## 11. User experience

### 11.1 Principles (the storyteller test)

Every screen is reviewed against the storyteller: could she finish this without help? Each step is scored for
clarity, confidence, recovery and cognitive load, and any Medium or High friction becomes a ticket with a
non-technical acceptance criterion. The review log is kept in `docs/` and appended to at every milestone.

Concrete rules:

- One primary action per screen. Technical choices under "Advanced".
- Plain words. "Waiting to be placed", not "Unlinked Assets Inbox". "People to name", not "Unknown face groups".
  No "CF", "bbox", or raw JSON in the interface.
- Every action gives visible feedback where the user is looking: a toast or inline state, not a string in a drawer.
- Every failure says what happened and what to do next. Nothing fails silently.
- No dead ends: wherever a list is empty or a thing is missing, the way to create it is right there.
- Confirmation of destination after capture, with one tap to change it.

### 11.2 Screens

| Screen | Purpose |
|---|---|
| **Home** | Record and Add photos, "Questions for you", recent memories, and the entry to the timeline. Fits a phone. |
| **Timeline** | Periods, epics, events with zoom (weights), expand and collapse that survives navigation, thread filter, search. |
| **Event** | Its own page: summary, memories with players, photos, people in photos, questions, actions. Shareable URL. |
| **Waiting to be placed** | The inbox (5.4). |
| **People**, **Person** | Directory and page (7.1). |
| **People to name** | Face clusters (7.4). |
| **Places**, **Place** | Directory and page (7.1). |
| **Photo** | Full view with face boxes toggle, metadata, map link, narrations, "tell the story", actions. Escape closes. |
| **Jobs** | What is running and what failed, with retry. |
| **Settings** | Archive settings, AI providers and switches, users and invitations, export, trash. |
| **Profile** | Name, password, sessions, sign out everywhere. |

### 11.3 Navigation and state

- Expanded and collapsed state, sort orders, filters and the directory tab persist across navigation (URL state or
  local storage), so opening a person and coming back does not reset the timeline.
- Deep links to every entity. Back works.
- Data loads per entity and updates optimistically; a mutation updates what changed, not the whole dataset.
- No global lock: a running job never disables unrelated controls.

### 11.4 Mobile

- Works on a phone screen first. Recording, adding photos, answering a question, browsing the timeline and playing
  memories are all one-hand tasks.
- Installable as a PWA with a home-screen icon and, should, a share target for photos.

### 11.5 Accessibility

- Every interactive element is a real button or link with a name, keyboard focus and a visible focus ring. No
  clickable headings, no icon-only emoji buttons without labels.
- Text at 16 px minimum, contrast to WCAG AA, a large-text mode. Audio players have visible controls.

### 11.6 v0 usability defects that must not recur

- Status messages rendered only inside a closed drawer.
- "Answer this" that scrolls to the top and hides the prompt in a closed drawer.
- Recording started with no visible Stop.
- Editing controls that render only when a card is expanded, or not at all (the sidebar's rename, merge, split).
- A desktop drawer with no Close button.
- A date override honoured on one upload path and ignored on two others.
- Delete with no confirmation (v0's person page).
- A setting that can be set once and never changed (the storyteller's name).

## 12. Engineering constraints

Carried over from the standards overhaul (PR #1) and the state of the v0 code.

- **murphy360/standards from the first commit:** shared CI (standards-check, python-lint or node-lint, actionlint,
  test-docker, image), ruff and Prettier at their defaults, the code-rules ratchet starting from an empty baseline,
  Dependabot, `CLAUDE.md` from the template.
- **Size limits are limits.** No file over 800 lines, no function over complexity 15, from day one. v0's `main.py`
  and `page.tsx` are the reason for the rewrite; the ratchet stops it happening again.
- **Tests from day one.** Every route has a test against a throwaway database. Every pipeline stage has a unit test
  with the AI and face providers faked. The date parser has a table test. Tests run in the Docker image.
- **Shape.** One API with routers per resource and a service per domain (accounts, capture, timeline, analysis,
  faces, directory, jobs, export). A worker process runs jobs from a job table with retries, idempotency keys and
  progress; the API never calls a provider inside a request except transcription of a short recording, and even that
  should be a job. Progress reaches the browser by SSE or job polling.
- **Data.** PostgreSQL with Alembic migrations and enforced foreign keys. Blobs in one content-addressed store
  (`/data/blobs/<sha256>`) with a `blobs` table; audio, originals, display photos, documents and thumbnails are all
  blobs. Thumbnails are generated once and cached.
- **API.** Every list is paginated. Every mutation returns the changed entity. Errors are structured (code, message,
  field). OpenAPI is generated and the frontend client is typed from it.
- **Frontend.** Components under 300 lines, no component with more than a dozen props, server state in a query cache
  (per-entity fetching, optimistic updates), UI state in the URL or local storage.
- **Configuration.** Environment variables with one typed settings object, documented in one place. Provider settings
  read at startup, not at import.
- **Hosting.** One image per process (api, web, worker), same origin under a base path (`/memoir`) behind Caddy on
  dontpanic, health checks, data in `/docker/memoir`. The deployment shape from PR #1 stays valid; Caddy's basic
  auth goes once the app's own login is live.
- **Providers behind interfaces.** AI (Gemini first), faces (CompreFace first), geocoding (Nominatim first), each a
  small adapter with a fake for tests.
- **Times are UTC** in the database; the UI shows the archive's time zone.
- **Observability.** Structured logs with request and job ids, a metrics endpoint, and a jobs page in the UI.

## 13. Out of scope for version 1

- Multiple archives in one deployment (the column exists; the UI does not).
- Embeddings and semantic search (the v0 README planned pgvector; full-text search is enough for now).
- Notifications beyond the optional weekly question.
- PDF export (HTML export ships first).
- Native mobile apps (PWA instead).
- Public sharing links.

## 14. Decisions for the owner

1. Viewers in version 1, or everyone a contributor?
2. Passkeys alongside passwords?
3. Per-memory "only me" visibility in version 1?
4. Encryption: encrypted volume, or application-level blob encryption?
5. Same repository (`murphy360/memoir`, v0 kept on a branch or tag) or a new one?
6. Frontend stack: stay with Next.js, or a lighter SPA (Vite plus React) since nothing renders on the server?
7. Auto-file the storyteller's quick memories, or always confirm placement?
8. Keep original audio forever, or 30 days?
9. HEIC support in version 1 (needs a converter in the image) or later?

## Appendix A. v0 API surface, for reference

87 routes under `/api`, all synchronous, none paginated, no auth. Grouped: memories (11), assets and photos (12),
events (13), epics (5), periods (8), threads (4), people (15), places (4), faces (4), unknown face groups (4),
questions (3), settings (2), compreface (1), health (2). Routes the v0 frontend never called: photo queue (2),
sync-faces, every unknown-face-group route, and document-memory creation. The rewrite's API is designed from
sections 3 to 10, not from this list.

## Appendix B. v0 defaults worth keeping as starting values

| Setting | v0 default |
|---|---|
| AI model | `gemini-2.5-flash`, overrides for research and photo passes |
| Transcription timeout | 45 s per attempt |
| Metadata extraction timeout | 30 s |
| Research timeout, max output | 90 s, 3000 tokens, 8 queries, 8 sources |
| Event summary | temperature 0.2, 1500 tokens, up to 20 memories and 20 assets as input |
| Photo pass 1 / pass 2 | temperature 1.0 / 0.1, 90 s each, notes capped 1500 chars |
| Photo display size | longest edge 2048, JPEG quality 85 |
| Face detection probability | 0.75 |
| Face candidates per face | 3 |
| Minimum recognition similarity | 0.90 |
| Auto-assign similarity | 0.92 |
| Face box overlap (IoU) to drop | 0.42 |
| Face thumbnail | 96 px, padding 0.35, cached one day |
| Reverse geocode cache | 3 decimal places (about 111 m), 5 s timeout |
| Audio normalisation | mono, 44.1 kHz, 128 kbps MP3 |
| Context caps into prompts | event title 180, date 100, description 500, memory excerpt 700, research context 20000 |

## Appendix C. v0 defects the rewrite must not repeat

- Startup backfills that recomputed dates and re-read EXIF on every boot, reverting manual edits.
- Deleted auto-created events recreated by the next startup.
- Face re-runs that deleted every face row, losing manual assignments.
- Foreign keys declared but never enforced, leaving dangling references after deletes and splits.
- Deleting a memory removed a file that an asset still pointed at.
- Merging periods silently deleted their epics.
- A person's recogniser identity stored sometimes as an id and sometimes as a name, and renames that broke the link.
- Research questions added without de-duplication; de-duplication only at read time.
- An in-memory photo queue lost on restart and unsafe with more than one worker.
- API keys in URL query strings.
- No rate limiting on a third-party geocoder whose policy is one request per second.
- A "processed" flag, a "may overwrite" flag and a title suggestion all smuggled inside text fields.
