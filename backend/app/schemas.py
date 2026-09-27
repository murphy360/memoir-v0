from datetime import datetime
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResearchSourceResponse(BaseModel):
    title: str
    url: str


class ResearchDateSuggestion(BaseModel):
    estimated_date_text: str
    date_precision: str
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    reasoning: str


class EventEditSuggestionResponse(BaseModel):
    title: Optional[str] = None
    event_date_text: Optional[str] = None
    description: Optional[str] = None
    reasoning: str


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcript: str
    event_description: str
    estimated_date_text: Optional[str]
    estimated_date_sort: Optional[date] = Field(
        default=None, description="Normalized start date used for timeline sorting."
    )
    estimated_end_date_sort: Optional[date] = Field(
        default=None,
        description="Normalized end date inferred from estimated_date_text when available.",
    )
    date_precision: Optional[str]
    response_to_question_id: Optional[int]
    response_to_question_text: Optional[str]
    recorder_name: Optional[str]
    recorder_person_id: Optional[int]
    referenced_people: list[str] = Field(default_factory=list)
    referenced_locations: list[str] = Field(default_factory=list)
    emotional_tone: str
    follow_up_question: str
    research_summary: Optional[str]
    research_queries: list[str] = Field(default_factory=list)
    research_sources: list[ResearchSourceResponse] = Field(default_factory=list)
    research_suggested_metadata: Optional[ResearchDateSuggestion] = None
    audio_size_bytes: Optional[int]
    audio_url: Optional[str]
    document_filename: Optional[str]
    document_size_bytes: Optional[int]
    document_url: Optional[str]
    date_recorded: Optional[date]
    created_at: datetime


class LifePeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: Optional[str]
    start_date_text: Optional[str]
    end_date_text: Optional[str]
    start_sort: Optional[date] = Field(
        default=None, description="Normalized period start date used for sorting."
    )
    end_sort: Optional[date] = Field(
        default=None,
        description="Normalized period end date used for range comparisons.",
    )
    summary: Optional[str]
    event_count: int = 0
    epic_count: int = Field(
        default=0, description="How many epics belong to this period."
    )
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreateLifePeriodRequest(BaseModel):
    title: str
    start_date_text: Optional[str] = None
    end_date_text: Optional[str] = None
    summary: Optional[str] = None


class AnalyzeLifePeriodRequest(BaseModel):
    apply_dates: bool = Field(
        default=False,
        description="Apply recommended period start/end dates to the period record.",
    )
    apply_title: bool = Field(
        default=False, description="Apply the top recommended period title."
    )
    apply_title_text: Optional[str] = Field(
        default=None,
        description="Apply this exact title text to the period when provided.",
    )
    regenerate_summary: bool = Field(
        default=False,
        description="Force writing a refreshed period summary back to the period.",
    )
    reanalyze_events: bool = Field(
        default=False,
        description="Force re-running event asset/memory analysis even when inputs are unchanged.",
    )


class UpdateLifePeriodRequest(BaseModel):
    title: Optional[str] = None
    start_date_text: Optional[str] = None
    end_date_text: Optional[str] = None


class LifeThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: Optional[str]
    summary: Optional[str]
    event_count: int = 0
    epic_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreateLifeThreadRequest(BaseModel):
    title: str = Field(description="Display title for this top-level life track.")
    summary: Optional[str] = Field(
        default=None, description="Optional narrative summary for the thread."
    )


class UpdateLifeThreadRequest(BaseModel):
    title: Optional[str] = Field(
        default=None, description="Updated display title for the life thread."
    )
    summary: Optional[str] = Field(
        default=None, description="Updated optional narrative summary for the thread."
    )


class LifeEpicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: int
    thread_id: Optional[int] = Field(
        default=None, description="Optional parent thread id for cross-period tagging."
    )
    title: str
    description: Optional[str]
    weight: int = Field(description="Visual prominence from 1 (light) to 10 (high).")
    start_date_text: Optional[str]
    end_date_text: Optional[str]
    start_sort: Optional[date] = Field(
        default=None, description="Normalized epic start date used for sorting."
    )
    end_sort: Optional[date] = Field(
        default=None, description="Normalized epic end date used for range comparisons."
    )
    event_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreateLifeEpicRequest(BaseModel):
    period_id: int = Field(description="Parent period id for this epic.")
    thread_id: Optional[int] = Field(
        default=None, description="Optional thread id for cross-period tagging."
    )
    title: str = Field(description="Display title for this event grouping.")
    description: Optional[str] = Field(
        default=None, description="Optional details about this grouping."
    )
    weight: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Visual prominence from 1 (light) to 10 (high).",
    )
    start_date_text: Optional[str] = Field(
        default=None, description="Optional textual start date for this epic."
    )
    end_date_text: Optional[str] = Field(
        default=None, description="Optional textual end date for this epic."
    )


class UpdateLifeEpicRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="Updated epic title.")
    period_id: Optional[int] = Field(
        default=None, description="Move this epic into another period."
    )
    thread_id: Optional[int] = Field(
        default=None, description="Set or clear the thread association for this epic."
    )
    description: Optional[str] = Field(
        default=None, description="Updated epic description."
    )
    weight: Optional[int] = Field(
        default=None, ge=1, le=10, description="Updated visual prominence from 1 to 10."
    )
    start_date_text: Optional[str] = Field(
        default=None, description="Updated textual start date."
    )
    end_date_text: Optional[str] = Field(
        default=None, description="Updated textual end date."
    )


class MergePeriodsRequest(BaseModel):
    into_period_id: int  # events/assets from the deleted period move here


class LifePeriodAnalysisResponse(BaseModel):
    period_id: int
    event_count: int
    asset_count: int
    coverage_ok: bool
    coverage_reasoning: str
    current_title: str
    recommended_titles: list[str] = []
    title_reasoning: str
    current_start_date_text: Optional[str] = None
    current_end_date_text: Optional[str] = None
    recommended_start_date_text: Optional[str] = None
    recommended_end_date_text: Optional[str] = None
    generated_summary: Optional[str] = None
    summary_reasoning: str
    queued_event_count: int = Field(
        default=0,
        description="How many period events were queued for analysis in this run.",
    )
    analyzed_event_count: int = Field(
        default=0, description="How many events were fully analyzed in this run."
    )
    skipped_event_count: int = Field(
        default=0,
        description="How many events were skipped because their analysis inputs were unchanged.",
    )
    failed_event_count: int = Field(
        default=0, description="How many event analysis attempts failed."
    )
    photo_assets_analyzed: int = Field(
        default=0,
        description="How many photo assets were processed while analyzing queued events.",
    )
    memories_researched: int = Field(
        default=0,
        description="How many linked memories were deeply researched while analyzing queued events.",
    )


class LifeEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: Optional[int]
    epic_id: Optional[int] = Field(
        default=None,
        description="Parent epic id when this event is grouped into an epic.",
    )
    thread_id: Optional[int] = Field(
        default=None, description="Parent thread id for cross-period narrative tagging."
    )
    title: str
    description: Optional[str]
    weight: int = Field(description="Visual prominence from 1 (light) to 10 (high).")
    summary: Optional[str]
    research_summary: Optional[str]
    research_queries: list[str] = Field(default_factory=list)
    research_sources: list[ResearchSourceResponse] = Field(default_factory=list)
    research_suggested_edit: Optional[EventEditSuggestionResponse] = None
    location: Optional[str]
    event_date_text: Optional[str]
    event_date_sort: Optional[date] = Field(
        default=None, description="Normalized event start date used for sorting."
    )
    event_end_date_sort: Optional[date] = Field(
        default=None,
        description="Normalized event end date when a date range is inferred.",
    )
    date_precision: Optional[str]
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    legacy_memory_id: Optional[int]
    linked_memory_ids: list[int] = Field(default_factory=list)
    legacy_audio_url: Optional[str]
    legacy_audio_size_bytes: Optional[int]
    linked_asset_count: int = 0
    analysis_status: Optional[str] = Field(
        default=None,
        description="Latest event analysis state such as running, completed, skipped, or failed.",
    )
    analysis_last_analyzed_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the most recent successful event analysis.",
    )
    analysis_last_error: Optional[str] = Field(
        default=None,
        description="Truncated error from the most recent failed event analysis attempt.",
    )
    created_at: datetime
    updated_at: datetime


class CreateLifeEventRequest(BaseModel):
    title: str
    period_id: Optional[int] = Field(
        default=None,
        description="Direct parent period id when this event is not grouped under an epic.",
    )
    epic_id: Optional[int] = Field(
        default=None,
        description="Optional epic id; when provided, period_id resolves from the epic.",
    )
    weight: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Visual prominence from 1 (light) to 10 (high).",
    )
    description: Optional[str] = None
    location: Optional[str] = None
    event_date_text: Optional[str] = None
    date_precision: Optional[str] = None
    date_year: Optional[int] = None
    date_month: Optional[int] = None
    date_day: Optional[int] = None
    date_decade: Optional[int] = None


class MergeLifeEventRequest(BaseModel):
    into_event_id: int


class UpdateLifeEventRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    event_date_text: Optional[str] = None
    period_id: Optional[int] = None
    epic_id: Optional[int] = Field(
        default=None, description="Set or clear epic membership for this event."
    )
    thread_id: Optional[int] = Field(
        default=None, description="Set or clear thread association for this event."
    )
    weight: Optional[int] = Field(
        default=None, ge=1, le=10, description="Updated visual prominence from 1 to 10."
    )


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: Optional[int]
    kind: str
    title: Optional[str]
    gemini_suggested_title: Optional[str] = Field(
        default=None, description="Most recent Gemini-recommended title for this asset."
    )
    legacy_memory_id: Optional[int]
    original_filename: Optional[str]
    content_type: Optional[str]
    size_bytes: Optional[int]
    captured_at: Optional[datetime]
    captured_end_at: Optional[datetime] = Field(
        default=None,
        description="Normalized asset end datetime; defaults to captured_at when no range exists.",
    )
    captured_at_text: Optional[str]
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    exif_place_name: Optional[str] = Field(
        default=None,
        description="Place text derived directly from EXIF tags when available.",
    )
    reverse_geocode_location_name: Optional[str] = Field(
        default=None,
        description="Locality resolved from EXIF GPS coordinates via reverse geocoding.",
    )
    analyzed_place_name: Optional[str] = Field(
        default=None,
        description="Gemini-assessed place inferred from visual and metadata context.",
    )
    location_name: Optional[str] = None
    camera_make: Optional[str]
    camera_model: Optional[str]
    lens_model: Optional[str]
    orientation: Optional[int]
    image_width: Optional[int]
    image_height: Optional[int]
    playback_url: Optional[str]
    text_excerpt: Optional[str]
    notes: Optional[str]
    download_url: str
    linked_event_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class LinkAssetToEventRequest(BaseModel):
    relation_type: Optional[str] = "evidence"


class UpdateAssetRequest(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    captured_at_text: Optional[str] = Field(
        default=None,
        description="Manual captured date/time text override used to correct EXIF dates.",
    )


class EventFaceResponse(BaseModel):
    id: int = Field(description="Face detection row id.")
    asset_id: int = Field(description="Photo asset id that contains the detected face.")
    asset_title: Optional[str] = Field(
        default=None, description="Best display title of the source photo asset."
    )
    asset_download_url: str = Field(description="Download URL for the source photo.")
    bbox_x: float = Field(
        description="Left coordinate normalized to [0, 1] of image width."
    )
    bbox_y: float = Field(
        description="Top coordinate normalized to [0, 1] of image height."
    )
    bbox_w: float = Field(description="Box width normalized to [0, 1] of image width.")
    bbox_h: float = Field(
        description="Box height normalized to [0, 1] of image height."
    )
    confidence: Optional[float] = Field(
        default=None, description="Detector confidence when available."
    )
    compreface_subject: Optional[str] = Field(
        default=None,
        description="Top CompreFace subject prediction for this face, if any.",
    )
    compreface_similarity: Optional[float] = Field(
        default=None,
        description="Similarity score for top CompreFace subject prediction in [0, 1].",
    )
    compreface_gender: Optional[str] = Field(
        default=None,
        description="CompreFace gender plugin value for this face when enabled.",
    )
    compreface_age_low: Optional[int] = Field(
        default=None,
        description="CompreFace age plugin lower bound for this face when enabled.",
    )
    compreface_age_high: Optional[int] = Field(
        default=None,
        description="CompreFace age plugin upper bound for this face when enabled.",
    )
    compreface_raw: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full raw CompreFace metadata object captured for this detected face.",
    )
    person_id: Optional[int] = Field(
        default=None,
        description="Assigned person id for this face, if manually linked.",
    )
    person_name: Optional[str] = Field(
        default=None, description="Assigned person display name, if manually linked."
    )


class AssignFacePersonRequest(BaseModel):
    person_id: Optional[int] = Field(
        default=None, description="Person id to assign, or null to clear assignment."
    )


class RenameFaceSubjectRequest(BaseModel):
    new_subject_name: str = Field(
        description="New CompreFace subject display name to apply."
    )


class UnknownFaceGroupMemberResponse(BaseModel):
    face_id: int = Field(
        description="Detected face row id belonging to this unknown group."
    )
    asset_id: int = Field(description="Source photo asset id for this detected face.")
    asset_download_url: str = Field(
        description="Download URL for the source photo asset."
    )
    bbox_x: float = Field(
        description="Left coordinate normalized to [0, 1] of image width."
    )
    bbox_y: float = Field(
        description="Top coordinate normalized to [0, 1] of image height."
    )
    bbox_w: float = Field(description="Box width normalized to [0, 1] of image width.")
    bbox_h: float = Field(
        description="Box height normalized to [0, 1] of image height."
    )
    confidence: Optional[float] = Field(
        default=None, description="Detector confidence when available."
    )


class UnknownFaceGroupResponse(BaseModel):
    group_id: int = Field(description="Unknown face group id.")
    fingerprint: str = Field(
        description="Deterministic grouping fingerprint shared by unknown faces in this group."
    )
    status: str = Field(
        description="Group lifecycle status such as open, ignored, or resolved."
    )
    representative_face_id: Optional[int] = Field(
        default=None,
        description="One face id selected as this group's representative sample.",
    )
    face_count: int = Field(
        description="How many face rows currently belong to this group."
    )
    members: list[UnknownFaceGroupMemberResponse] = Field(
        default_factory=list,
        description="Face members for rapid review and assignment.",
    )


class AssignUnknownFaceGroupRequest(BaseModel):
    person_id: int = Field(
        description="Existing person id to assign to all faces in this unknown group."
    )


class CreatePersonFromUnknownFaceGroupRequest(BaseModel):
    name: str = Field(
        description="New person display name created from this unknown group."
    )


class MergeUnknownFaceGroupRequest(BaseModel):
    into_group_id: int = Field(
        description="Target unknown group id that will receive all faces from the source group."
    )


class SplitUnknownFaceGroupRequest(BaseModel):
    face_ids: list[int] = Field(
        default_factory=list,
        description="Face ids to move from the source group into a newly created group.",
    )


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    source_memory_id: Optional[int]
    status: str
    created_at: datetime


class DirectoryEntryResponse(BaseModel):
    id: int = Field(description="Directory entry id.")
    name: str = Field(description="Display name of the directory entry.")
    memory_count: int = Field(
        description="How many memories currently reference this entry."
    )
    photo_count: int = Field(
        default=0,
        description="How many distinct photo assets are linked to this person.",
    )
    aliases: list[str] = Field(default_factory=list)
    avatar_download_url: Optional[str] = Field(
        default=None,
        description="Photo URL for this person card avatar, when available.",
    )
    compreface_subject_id: Optional[str] = Field(
        default=None,
        description="CompreFace subject identifier linked 1:1 to this person when enrolled.",
    )
    compreface_subject_url: Optional[str] = Field(
        default=None,
        description="Direct CompreFace API URL for the linked subject when available.",
    )


class CreateDirectoryEntryRequest(BaseModel):
    name: str


class UpdateDirectoryEntryRequest(BaseModel):
    name: str


class MergePersonRequest(BaseModel):
    into_person_id: int


class LinkPersonComprefaceRequest(BaseModel):
    subject_name: Optional[str] = Field(
        default=None,
        description="Existing CompreFace subject name to link, or empty to auto-match by person name.",
    )


class SplitPersonRequest(BaseModel):
    new_names: list[str]
    keep_alias: bool = True


class AddAliasRequest(BaseModel):
    alias: str


class UpdatePersonContactRequest(BaseModel):
    phone: Optional[str] = Field(
        default=None, description="Updated phone number for the person; null clears it."
    )
    email: Optional[str] = Field(
        default=None, description="Updated email for the person; null clears it."
    )
    address: Optional[str] = Field(
        default=None, description="Updated mailing or home address; null clears it."
    )
    notes: Optional[str] = Field(
        default=None, description="Free-form person notes shown in person details."
    )
    birthday_text: Optional[str] = Field(
        default=None, description="Free-text birthday value supporting fuzzy dates."
    )


class PersonContactResponse(BaseModel):
    phone: Optional[str] = Field(
        default=None, description="Person phone number as entered by the user."
    )
    email: Optional[str] = Field(
        default=None, description="Person email address as entered by the user."
    )
    address: Optional[str] = Field(
        default=None, description="Person address text as entered by the user."
    )
    notes: Optional[str] = Field(
        default=None, description="Free-form notes about this person."
    )
    birthday_text: Optional[str] = Field(
        default=None, description="Free-text birthday string."
    )


class PersonDetailResponse(BaseModel):
    id: int = Field(description="Person id.")
    name: str = Field(description="Person display name.")
    aliases: list[str] = Field(
        default_factory=list, description="All known aliases for this person."
    )
    memory_count: int = Field(default=0, description="Count of related memories.")
    event_count: int = Field(default=0, description="Count of related events.")
    photo_count: int = Field(default=0, description="Count of related photo assets.")
    avatar_download_url: Optional[str] = Field(
        default=None, description="Avatar image URL chosen from related photo faces."
    )
    compreface_subject_id: Optional[str] = Field(
        default=None, description="Linked CompreFace subject id or name."
    )
    compreface_subject_url: Optional[str] = Field(
        default=None, description="CompreFace subject URL when configured."
    )
    contact: PersonContactResponse = Field(
        description="Contact details block for this person."
    )


class PersonActivityResponse(BaseModel):
    memories: list[MemoryResponse] = Field(
        default_factory=list, description="Memories associated to this person."
    )
    events: list[LifeEventResponse] = Field(
        default_factory=list, description="Events associated to this person."
    )
    assets: list[AssetResponse] = Field(
        default_factory=list, description="Photo assets associated to this person."
    )


class CreatePersonQuickMemoryRequest(BaseModel):
    text: str = Field(description="Short memory text about this person.")
    estimated_date_text: Optional[str] = Field(
        default=None, description="Optional free-text estimated date for the memory."
    )


class ApprovePersonFaceRequest(BaseModel):
    person_id: int = Field(description="Person id to approve this face assignment for.")


class UpdateMemoryRecorderRequest(BaseModel):
    person_id: Optional[int] = None
    recorder_name: Optional[str] = None


class UpdateMemoryRequest(BaseModel):
    event_description: Optional[str] = None
    estimated_date_text: Optional[str] = Field(
        default=None,
        description="Updated textual memory date; supports year/month/day and ranges.",
    )


class AnswerQuestionRequest(BaseModel):
    answer_memory_id: Optional[int] = None


class SettingsResponse(BaseModel):
    main_character_name: Optional[str] = None


class UpdateSettingRequest(BaseModel):
    value: Optional[str] = None
