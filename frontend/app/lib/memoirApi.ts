import {
  AppSettings,
  AssetEntry,
  DirectoryEntry,
  EventFaceEntry,
  LifeEpic,
  LifeEvent,
  LifePeriod,
  LifePeriodAnalysis,
  LifeThread,
  MemoryEntry,
  PersonActivity,
  PersonDetail,
  Question,
} from "../types";

/** Where the API lives: an absolute URL when given, else the same origin under the base path. */
export function apiBaseFrom(apiBaseUrl?: string, basePath?: string): string {
  return apiBaseUrl || basePath || "";
}

export const API_BASE = apiBaseFrom(
  process.env.NEXT_PUBLIC_API_BASE_URL,
  process.env.NEXT_PUBLIC_BASE_PATH,
);

function toAbsoluteApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

async function expectOk(response: Response, message: string): Promise<void> {
  if (!response.ok) {
    let detail = "";
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json().catch(() => null);
      if (data && typeof data.detail === "string") {
        detail = data.detail;
      } else if (data) {
        detail = JSON.stringify(data);
      }
    } else {
      detail = await response.text().catch(() => "");
    }
    throw new Error(detail ? `${message}: ${detail}` : message);
  }
}

/**
 * Send a JSON PATCH request and return a parsed response body.
 * Used to keep Period/Epic/Event mutation calls on one shared code path.
 */
async function patchJson<T>(
  path: string,
  payload: unknown,
  message: string,
): Promise<T> {
  const response = await fetch(toAbsoluteApiUrl(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, message);
  return response.json();
}

export function resolveApiUrl(path: string): string {
  return toAbsoluteApiUrl(path);
}

export type TimelineBundle = {
  memories: MemoryEntry[];
  questions?: Question[];
  people?: DirectoryEntry[];
  places?: DirectoryEntry[];
  settings?: AppSettings;
  threads?: LifeThread[];
  periods?: LifePeriod[];
  epics?: LifeEpic[];
  events?: LifeEvent[];
  unlinkedAssets?: AssetEntry[];
};

export async function fetchTimelineBundle(): Promise<TimelineBundle> {
  const [
    memoriesRes,
    questionsRes,
    peopleRes,
    placesRes,
    settingsRes,
    threadsRes,
    periodsRes,
    epicsRes,
    eventsRes,
    unlinkedAssetsRes,
  ] = await Promise.all([
    fetch(toAbsoluteApiUrl("/api/memories"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/questions"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/people"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/places"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/settings"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/threads"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/periods"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/epics"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/events"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/assets/unlinked"), { cache: "no-store" }),
  ]);

  await expectOk(memoriesRes, "Failed to load timeline");

  const bundle: TimelineBundle = {
    memories: await memoriesRes.json(),
  };

  if (questionsRes.ok) {
    bundle.questions = await questionsRes.json();
  }
  if (peopleRes.ok) {
    bundle.people = await peopleRes.json();
  }
  if (placesRes.ok) {
    bundle.places = await placesRes.json();
  }
  if (settingsRes.ok) {
    bundle.settings = await settingsRes.json();
  }
  if (threadsRes.ok) {
    bundle.threads = await threadsRes.json();
  }
  if (periodsRes.ok) {
    bundle.periods = await periodsRes.json();
  }
  if (epicsRes.ok) {
    bundle.epics = await epicsRes.json();
  }
  if (eventsRes.ok) {
    bundle.events = await eventsRes.json();
  }
  if (unlinkedAssetsRes.ok) {
    bundle.unlinkedAssets = await unlinkedAssetsRes.json();
  }

  return bundle;
}

export async function fetchEventAssets(eventId: number): Promise<AssetEntry[]> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/assets`),
    { cache: "no-store" },
  );
  await expectOk(response, "Failed to load event assets");
  return response.json();
}

/** Load detected faces for one event from GET /api/events/{event_id}/faces. */
export async function fetchEventFaces(
  eventId: number,
): Promise<EventFaceEntry[]> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/faces`),
    { cache: "no-store" },
  );
  await expectOk(response, "Failed to load event faces");
  return response.json();
}

/** Assign or clear person link for a detected face via POST /api/faces/{face_id}/assign-person. */
export async function assignFacePerson(
  faceId: number,
  personId: number | null,
): Promise<EventFaceEntry> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/faces/${faceId}/assign-person`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId }),
    },
  );

  await expectOk(response, "Failed to assign face");
  return response.json();
}

/** Rename a detected face's CompreFace subject via POST /api/faces/{face_id}/rename-subject. */
export async function renameFaceSubject(
  faceId: number,
  newSubjectName: string,
): Promise<EventFaceEntry> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/faces/${faceId}/rename-subject`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_subject_name: newSubjectName }),
    },
  );

  await expectOk(response, "Failed to rename CompreFace subject");
  return response.json();
}

/** Permanently delete a detected face record via DELETE /api/faces/{face_id}. */
export async function deleteFace(faceId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/faces/${faceId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Failed to delete face");
}

export async function createPeriod(payload: {
  title: string;
  start_date_text: string | null;
  end_date_text: string | null;
  summary: string | null;
}): Promise<LifePeriod> {
  const response = await fetch(toAbsoluteApiUrl("/api/periods"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create period failed");
  return response.json();
}

/** Create a top-level thread via POST /api/threads. */
export async function createThread(payload: {
  title: string;
  summary: string | null;
}): Promise<LifeThread> {
  const response = await fetch(toAbsoluteApiUrl("/api/threads"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create thread failed");
  return response.json();
}

/** Create an epic inside a period via POST /api/epics. */
export async function createEpic(payload: {
  period_id: number;
  title: string;
  description: string | null;
  weight: number;
  start_date_text: string | null;
  end_date_text: string | null;
}): Promise<LifeEpic> {
  const response = await fetch(toAbsoluteApiUrl("/api/epics"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create epic failed");
  return response.json();
}

/** Delete a thread via DELETE /api/threads/{thread_id}. */
export async function deleteThread(threadId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/threads/${threadId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete thread failed");
}

/** Delete an epic via DELETE /api/epics/{epic_id}. */
export async function deleteEpic(epicId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/epics/${epicId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete epic failed");
}

/** Assign or clear a thread on an epic via PATCH /api/epics/{epic_id}. */
export async function assignEpicToThread(
  epicId: number,
  threadId: number | null,
): Promise<LifeEpic> {
  return updateEpicById(epicId, { thread_id: threadId });
}

/** Move an epic into a different period via PATCH /api/epics/{epic_id}. */
export async function assignEpicToPeriod(
  epicId: number,
  periodId: number,
): Promise<LifeEpic> {
  return updateEpicById(epicId, { period_id: periodId });
}

/** Assign or clear a thread on an event via PATCH /api/events/{event_id}. */
export async function assignEventToThread(
  eventId: number,
  threadId: number | null,
): Promise<LifeEvent> {
  return updateEventById(eventId, { thread_id: threadId });
}

/** Rename a thread via PATCH /api/threads/{thread_id}. */
export async function renameThread(
  threadId: number,
  title: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/threads/${threadId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await expectOk(response, "Failed to rename thread");
}

/** Rename an epic via PATCH /api/epics/{epic_id}. */
export async function renameEpic(epicId: number, title: string): Promise<void> {
  await updateEpicById(epicId, { title });
}

/** Update an epic by id via PATCH /api/epics/{epic_id}. */
export async function updateEpicById(
  epicId: number,
  payload: {
    title?: string;
    period_id?: number;
    thread_id?: number | null;
    description?: string | null;
    weight?: number;
    start_date_text?: string | null;
    end_date_text?: string | null;
  },
): Promise<LifeEpic> {
  return patchJson<LifeEpic>(
    `/api/epics/${epicId}`,
    payload,
    "Failed to update epic",
  );
}

export async function createEvent(payload: {
  title: string;
  period_id: number | null;
  epic_id: number | null;
  weight: number;
  description: string | null;
  location: string | null;
  event_date_text: string | null;
}): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl("/api/events"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create event failed");
  return response.json();
}

export async function analyzeLifePeriod(
  periodId: number,
  payload: {
    apply_dates: boolean;
    apply_title: boolean;
    regenerate_summary: boolean;
    reanalyze_events?: boolean;
  },
): Promise<LifePeriodAnalysis> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/periods/${periodId}/analyze`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  await expectOk(response, "Analyze period failed");
  return response.json();
}

export async function renameEventTitle(
  eventId: number,
  title: string,
): Promise<void> {
  await updateEventById(eventId, { title });
}

export async function updateEventById(
  eventId: number,
  payload: {
    title?: string;
    event_date_text?: string | null;
    description?: string | null;
    location?: string | null;
    period_id?: number | null;
    epic_id?: number | null;
    thread_id?: number | null;
    weight?: number;
  },
): Promise<LifeEvent> {
  return patchJson<LifeEvent>(
    `/api/events/${eventId}`,
    payload,
    "Failed to update event",
  );
}

export async function renamePeriodTitle(
  periodId: number,
  title: string,
): Promise<void> {
  await updatePeriodById(periodId, { title });
}

export async function updatePeriodDates(
  periodId: number,
  startDateText: string | null,
  endDateText: string | null,
): Promise<void> {
  await updatePeriodById(periodId, {
    start_date_text: startDateText,
    end_date_text: endDateText,
  });
}

/** Update a period by id via PATCH /api/periods/{period_id}. */
export async function updatePeriodById(
  periodId: number,
  payload: {
    title?: string;
    start_date_text?: string | null;
    end_date_text?: string | null;
  },
): Promise<LifePeriod> {
  return patchJson<LifePeriod>(
    `/api/periods/${periodId}`,
    payload,
    "Failed to update period",
  );
}

export async function deletePeriodById(periodId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${periodId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Failed to delete period");
}

export async function mergePeriodInto(
  fromPeriodId: number,
  intoPeriodId: number,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/periods/${fromPeriodId}/merge`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ into_period_id: intoPeriodId }),
    },
  );
  await expectOk(response, "Failed to merge period");
}

export async function uploadAsset(formData: FormData): Promise<AssetEntry> {
  const response = await fetch(toAbsoluteApiUrl("/api/assets"), {
    method: "POST",
    body: formData,
  });
  await expectOk(response, "Upload asset failed");
  return response.json();
}

/** Process event photos via POST /api/assets/photos/process-events, optionally including already-processed assets for re-runs. */
export async function processEventPhotoAssets(
  eventId: number,
  includeProcessed = false,
): Promise<{
  events_processed: number;
  photos_processed: number;
  processed_asset_ids: number[];
}> {
  const response = await fetch(
    toAbsoluteApiUrl("/api/assets/photos/process-events"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: eventId,
        include_processed: includeProcessed,
      }),
    },
  );
  await expectOk(response, "Process event photos failed");
  return response.json();
}

/** Process one photo asset via POST /api/assets/{asset_id}/process-photo. */
export async function processSinglePhotoAsset(
  assetId: number,
  includeProcessed = true,
): Promise<{
  asset_id: number;
  processed: boolean;
  has_text_excerpt: boolean;
  face_count: number;
  has_gps: boolean;
  exif_place_name: string | null;
  reverse_geocode_location_name: string | null;
  analyzed_place_name: string | null;
  location_name: string | null;
  captured_at_text: string | null;
  gemini_suggested_title: string | null;
  suggested_title: string | null;
}> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/assets/${assetId}/process-photo`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_processed: includeProcessed }),
    },
  );
  await expectOk(response, "Process photo failed");
  return response.json();
}

export async function deleteAsset(assetId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete asset failed");
}

export async function updateAssetNotes(
  assetId: number,
  notes: string | null,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  await expectOk(response, "Update asset notes failed");
}

export async function updateAssetTitle(
  assetId: number,
  title: string | null,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await expectOk(response, "Update asset title failed");
}

/**
 * PATCH /api/assets/{assetId}
 * Sends a manual captured date text override so backend normalization can replace or clear captured_at fields.
 */
export async function updateAssetCapturedDate(
  assetId: number,
  capturedAtText: string | null,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ captured_at_text: capturedAtText }),
  });
  await expectOk(response, "Update asset captured date failed");
}

export async function linkAssetToEvent(
  assetId: number,
  eventId: number,
  relationType: string,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/assets/${assetId}/link-event/${eventId}`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relation_type: relationType }),
    },
  );
  await expectOk(response, "Link asset failed");
}

export async function deleteEventById(eventId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete event failed");
}

export async function mergeEventInto(
  sourceId: number,
  targetId: number,
): Promise<LifeEvent> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${sourceId}/merge`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ into_event_id: targetId }),
    },
  );
  await expectOk(response, "Merge event failed");
  return response.json();
}

export async function summarizeEventById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/summarize`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Event summary failed");
  return response.json();
}

export async function researchEventById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/research`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Event research failed");
  return response.json();
}

export async function applyEventResearchSuggestionById(
  eventId: number,
): Promise<LifeEvent> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/apply-research-suggestion`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Apply event suggestion failed");
  return response.json();
}

export async function dismissEventResearchSuggestionById(
  eventId: number,
): Promise<LifeEvent> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/events/${eventId}/dismiss-research-suggestion`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Dismiss event suggestion failed");
  return response.json();
}

export async function dismissQuestionById(questionId: number): Promise<void> {
  await fetch(toAbsoluteApiUrl(`/api/questions/${questionId}/dismiss`), {
    method: "POST",
  });
}

export async function saveMainCharacterName(
  value: string | null,
): Promise<void> {
  await fetch(toAbsoluteApiUrl("/api/settings/main_character_name"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
}

export async function reanalyzeMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/memories/${memoryId}/reanalyze`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Reanalyze failed");
}

export async function researchMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/memories/${memoryId}/research`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Research failed");
}

export async function applyResearchSuggestionById(
  memoryId: number,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/memories/${memoryId}/apply-research-suggestion`),
    {
      method: "POST",
    },
  );
  await expectOk(response, "Apply failed");
}

export async function dismissResearchSuggestionById(
  memoryId: number,
): Promise<void> {
  await fetch(
    toAbsoluteApiUrl(`/api/memories/${memoryId}/dismiss-research-suggestion`),
    {
      method: "POST",
    },
  );
}

export async function deleteMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete failed");
}

export async function assignRecorderPerson(
  memoryId: number,
  personId: number,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/memories/${memoryId}/recorder`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId }),
    },
  );
  await expectOk(response, "Recorder update failed");
}

/** Load full person profile details via GET /api/people/{person_id}. */
export async function fetchPersonDetail(
  personId: number,
): Promise<PersonDetail> {
  const response = await fetch(toAbsoluteApiUrl(`/api/people/${personId}`), {
    cache: "no-store",
  });
  await expectOk(response, "Failed to load person details");
  return response.json();
}

/** Load person activity bundles via GET /api/people/{person_id}/activity. */
export async function fetchPersonActivity(
  personId: number,
): Promise<PersonActivity> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/activity`),
    { cache: "no-store" },
  );
  await expectOk(response, "Failed to load person activity");
  return response.json();
}

/** Load people directory rows for merge targets from GET /api/people. */
export async function fetchPeopleDirectory(): Promise<DirectoryEntry[]> {
  const response = await fetch(toAbsoluteApiUrl("/api/people"), {
    cache: "no-store",
  });
  await expectOk(response, "Failed to load people directory");
  return response.json();
}

/** Patch person contact fields via PATCH /api/people/{person_id}/contact. */
export async function updatePersonContact(
  personId: number,
  payload: {
    phone?: string | null;
    email?: string | null;
    address?: string | null;
    notes?: string | null;
    birthday_text?: string | null;
  },
): Promise<PersonDetail> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/contact`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  await expectOk(response, "Failed to update person contact details");
  return response.json();
}

/** Create a quick person-scoped text memory via POST /api/people/{person_id}/memories/quick. */
export async function createPersonQuickMemory(
  personId: number,
  payload: { text: string; estimated_date_text?: string | null },
): Promise<MemoryEntry> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/memories/quick`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  await expectOk(response, "Failed to create quick memory");
  return response.json();
}

/** Fetch pending suggested face matches for approval via GET /api/people/{person_id}/faces/suggested. */
export async function fetchPersonSuggestedFaces(
  personId: number,
): Promise<EventFaceEntry[]> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/faces/suggested`),
    { cache: "no-store" },
  );
  await expectOk(response, "Failed to load suggested faces");
  return response.json();
}

/** Approve one suggested face match and sync CompreFace via POST /api/people/{person_id}/faces/{face_id}/approve. */
export async function approvePersonFace(
  personId: number,
  faceId: number,
): Promise<EventFaceEntry> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/faces/${faceId}/approve`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: personId }),
    },
  );
  await expectOk(response, "Failed to approve face");
  return response.json();
}

export async function mergePeopleEntries(
  sourceId: number,
  intoId: number,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${sourceId}/merge`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ into_person_id: intoId }),
    },
  );
  await expectOk(response, "Merge failed");
}

/** Link one person to an existing CompreFace subject via POST /api/people/{person_id}/link-compreface. */
export async function linkPersonToCompreface(
  personId: number,
  subjectName: string,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/link-compreface`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_name: subjectName }),
    },
  );
  await expectOk(response, "CompreFace link failed");
}

/** Fetch list of available CompreFace subjects via GET /api/compreface/subjects. */
export async function getComprefaceSubjects(): Promise<string[]> {
  const response = await fetch(toAbsoluteApiUrl("/api/compreface/subjects"));
  await expectOk(response, "Failed to fetch CompreFace subjects");
  return response.json();
}

export async function splitPersonEntry(
  sourceId: number,
  newNames: string[],
  keepAlias: boolean,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${sourceId}/split`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_names: newNames, keep_alias: keepAlias }),
    },
  );
  await expectOk(response, "Split failed");
}

export async function addPersonAlias(
  personId: number,
  alias: string,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/aliases`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alias }),
    },
  );
  await expectOk(response, "Add alias failed");
}

export async function removePersonAlias(
  personId: number,
  alias: string,
): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(
      `/api/people/${personId}/aliases/${encodeURIComponent(alias)}`,
    ),
    { method: "DELETE" },
  );
  await expectOk(response, "Remove alias failed");
}

export async function createDirectoryEntry(
  kind: "people" | "places",
  name: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectOk(response, "Create failed");
}

/** Create one person via POST /api/people and return the created directory entry. */
export async function createPersonEntry(name: string): Promise<DirectoryEntry> {
  const response = await fetch(toAbsoluteApiUrl("/api/people"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectOk(response, "Create person failed");
  return response.json();
}

export async function renameDirectoryEntry(
  kind: "people" | "places",
  itemId: number,
  name: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}/${itemId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectOk(response, "Rename failed");
}

export async function deleteDirectoryEntry(
  kind: "people" | "places",
  itemId: number,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}/${itemId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete failed");
}

/**
 * Upload an audio recording as a memory.
 * relatedAssetId links the saved memory directly to a specific photo asset.
 * quickCapture marks one-tap home-screen captures so backend can apply quick-entry automation.
 */
export async function createMemoryFromAudioBlob(
  blob: Blob,
  eventId?: number,
  relatedAssetId?: number,
  quickCapture = false,
): Promise<MemoryEntry> {
  const formData = new FormData();
  formData.append("audio", blob, `memory-${Date.now()}.webm`);
  if (eventId !== undefined) {
    formData.append("event_id", String(eventId));
  }
  if (relatedAssetId !== undefined) {
    formData.append("related_asset_id", String(relatedAssetId));
  }
  if (quickCapture) {
    formData.append("quick_capture", "true");
  }

  const response = await fetch(toAbsoluteApiUrl("/api/memories"), {
    method: "POST",
    body: formData,
  });
  await expectOk(response, "Upload failed");
  return response.json();
}

export async function answerQuestionWithMemory(
  questionId: number,
  answerMemoryId: number,
): Promise<void> {
  await fetch(toAbsoluteApiUrl(`/api/questions/${questionId}/answer`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer_memory_id: answerMemoryId }),
  });
}

export async function updateMemoryTitle(
  memoryId: number,
  eventDescription: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_description: eventDescription }),
  });
  await expectOk(response, "Failed to update memory title");
}

export async function createMemoryFromDocument(
  formData: FormData,
  eventId?: number,
): Promise<MemoryEntry> {
  if (eventId !== undefined) {
    formData.append("event_id", String(eventId));
  }
  const response = await fetch(toAbsoluteApiUrl("/api/memories/document"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response
      .json()
      .catch(() => ({ detail: "Upload failed" }));
    throw new Error(errorData.detail || "Upload failed");
  }

  return response.json();
}
