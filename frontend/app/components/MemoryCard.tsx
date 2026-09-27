"use client";

import { useEffect, useState } from "react";
import { DirectoryEntry, MemoryEntry, Question } from "../types";

type MemoryCardProps = {
  memory: MemoryEntry;
  linkedQuestions: Question[];
  peopleOptions: DirectoryEntry[];
  formatBytes: (bytes: number) => string;
  resolveApiUrl: (path: string) => string;
  onAcceptSuggestion: (memoryId: number) => Promise<void>;
  onDismissSuggestion: (memoryId: number) => Promise<void>;
  onReanalyze: (memoryId: number) => Promise<void>;
  onDelete: (memoryId: number) => Promise<void>;
  onAssignRecorder: (memoryId: number, personId: number) => Promise<void>;
  isBusy: boolean;
  defaultExpanded?: boolean;
  hideHeader?: boolean;
  containerId?: string;
  isHighlighted?: boolean;
};

function asLabelList(items: string[]): string {
  if (items.length === 0) {
    return "Unknown";
  }
  return items.join(", ");
}

export function MemoryCard({
  memory,
  linkedQuestions,
  peopleOptions,
  formatBytes,
  resolveApiUrl,
  onAcceptSuggestion,
  onDismissSuggestion,
  onReanalyze,
  onDelete,
  onAssignRecorder,
  isBusy,
  defaultExpanded = false,
  hideHeader = false,
  containerId,
  isHighlighted = false,
}: MemoryCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded || hideHeader);
  const [selectedRecorder, setSelectedRecorder] = useState("");

  useEffect(() => {
    setIsExpanded(defaultExpanded || hideHeader);
  }, [memory.id, defaultExpanded, hideHeader]);

  useEffect(() => {
    setSelectedRecorder(
      memory.recorder_person_id ? `${memory.recorder_person_id}` : "",
    );
  }, [memory.id, memory.recorder_person_id]);

  const canAssignRecorder = !memory.recorder_name && selectedRecorder;

  return (
    <article
      id={containerId}
      className={`memory${isHighlighted ? " focusPulse" : ""}`}
    >
      {!hideHeader && (
        <div className="memoryHeader">
          <div className="memoryHeaderText">
            <h3>{memory.event_description}</h3>
            <div className="memoryDateSummary">
              <p className="meta">
                Date:{" "}
                <span className="badge">
                  {memory.estimated_date_text || "Unknown"}
                </span>
              </p>
              <p className="meta">
                Recorded:{" "}
                <span className="badge">
                  {memory.date_recorded || "Unknown"}
                </span>
              </p>
            </div>
          </div>
          <h4
            style={{
              cursor: "pointer",
              userSelect: "none",
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              margin: 0,
              padding: "0.2rem 0",
            }}
            onClick={() => setIsExpanded((current) => !current)}
            aria-expanded={isExpanded}
          >
            <span>{isExpanded ? "▾" : "▸"}</span>
            Details
          </h4>
        </div>
      )}

      {isExpanded && memory.response_to_question_text && (
        <p className="memoryResponseLink">
          <strong>In response to:</strong> {memory.response_to_question_text}
        </p>
      )}
      {isExpanded && (
        <div className="metaList">
          <p className="meta">
            Date precision:{" "}
            <span className="badge">{memory.date_precision || "unknown"}</span>
          </p>
          <p className="meta">
            Recorded by:{" "}
            <span className="badge">{memory.recorder_name || "Unknown"}</span>
          </p>
          <p className="meta">
            Locations:{" "}
            <span className="badge">
              {asLabelList(memory.referenced_locations || [])}
            </span>
          </p>
          <p className="meta">
            People:{" "}
            <span className="badge">
              {asLabelList(memory.referenced_people || [])}
            </span>
          </p>
          <p className="meta">
            Tone: <span className="badge">{memory.emotional_tone}</span>
          </p>
        </div>
      )}

      {isExpanded && !memory.recorder_name && (
        <div className="recorderAssign">
          <label className="meta" htmlFor={`recorder-${memory.id}`}>
            Assign recorder
          </label>
          <div className="recorderAssignControls">
            <select
              id={`recorder-${memory.id}`}
              className="micSelect"
              value={selectedRecorder}
              onChange={(event) => setSelectedRecorder(event.target.value)}
              disabled={isBusy || peopleOptions.length === 0}
            >
              <option value="">Select a person</option>
              {peopleOptions.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
            <button
              className="secondary"
              type="button"
              onClick={() =>
                onAssignRecorder(memory.id, Number(selectedRecorder))
              }
              disabled={!canAssignRecorder || isBusy}
            >
              Save Recorder
            </button>
          </div>
          {peopleOptions.length === 0 && (
            <p className="meta">
              No known people are available yet to assign as the recorder.
            </p>
          )}
        </div>
      )}

      {isExpanded && memory.audio_url && (
        <audio
          controls
          preload="metadata"
          src={resolveApiUrl(memory.audio_url)}
          style={{ width: "100%" }}
        />
      )}
      {isExpanded && <p>{memory.transcript}</p>}
      {isExpanded && memory.research_summary && (
        <section className="researchPanel">
          <p className="researchLabel">Research Notes</p>
          <pre className="researchSummary">{memory.research_summary}</pre>
          {memory.research_suggested_metadata && (
            <div className="suggestionBox">
              <p className="suggestionLabel">Suggested date update</p>
              <p className="suggestionDate">
                {memory.research_suggested_metadata.estimated_date_text}
              </p>
              <p className="suggestionMeta">
                Precision:{" "}
                <strong>
                  {memory.research_suggested_metadata.date_precision}
                </strong>
              </p>
              <p className="suggestionReasoning">
                {memory.research_suggested_metadata.reasoning}
              </p>
              <div className="suggestionActions">
                <button
                  className="primary"
                  type="button"
                  onClick={() => onAcceptSuggestion(memory.id)}
                  disabled={isBusy}
                >
                  Accept
                </button>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => onDismissSuggestion(memory.id)}
                  disabled={isBusy}
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}
          {memory.research_queries.length > 0 && (
            <div className="researchQueries">
              <p className="researchSubhead">Search queries used</p>
              <div className="researchQueryList">
                {memory.research_queries.map((query) => (
                  <span key={query} className="researchQueryChip">
                    {query}
                  </span>
                ))}
              </div>
            </div>
          )}
          {memory.research_sources.length > 0 && (
            <div className="researchSources">
              <p className="researchSubhead">Sources</p>
              <ul className="researchSourceList">
                {memory.research_sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {linkedQuestions.length > 0 && (
            <div className="researchLinkedQuestions">
              <p className="researchSubhead">
                Follow-up questions from research
              </p>
              <ul className="linkedQuestionList">
                {linkedQuestions.map((q) => (
                  <li key={q.id} className="linkedQuestionItem">
                    {q.text}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      {isExpanded && (
        <div className="memoryActions">
          <button
            className="secondary"
            type="button"
            onClick={() => onReanalyze(memory.id)}
            disabled={isBusy}
          >
            Reanalyze
          </button>
          <button
            className="ghost"
            type="button"
            onClick={() => onDelete(memory.id)}
            disabled={isBusy}
          >
            Delete Memory
          </button>
        </div>
      )}
    </article>
  );
}
