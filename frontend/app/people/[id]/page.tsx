"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { formatAssetCaptureDate } from "../../lib/homePageHelpers";
import {
  addPersonAlias,
  approvePersonFace,
  createPersonQuickMemory,
  deleteFace,
  deleteDirectoryEntry,
  fetchEventFaces,
  fetchPeopleDirectory,
  fetchPersonActivity,
  fetchPersonDetail,
  fetchPersonSuggestedFaces,
  linkPersonToCompreface,
  mergePeopleEntries,
  processSinglePhotoAsset,
  removePersonAlias,
  renameDirectoryEntry,
  splitPersonEntry,
  updatePersonContact,
  resolveApiUrl,
} from "../../lib/memoirApi";
import { PhotoDetailsModal } from "../../components/PhotoDetailsModal";
import {
  DirectoryEntry,
  EventFaceEntry,
  PersonActivity,
  PersonDetail,
} from "../../types";

type FaceImageSize = {
  width: number;
  height: number;
};

type PersonPhotoModalState = {
  isOpen: boolean;
  assetId: number | null;
  sourceDownloadPath: string | null;
  imageUrl: string;
  title: string;
  filename: string | null;
  capturedText: string | null;
  positionText: string | null;
  dimensionsText: string | null;
  notes: string | null;
  faces: EventFaceEntry[];
  focusFaceId: number | null;
};

export default function PersonDetailsPage() {
  const params = useParams<{ id: string }>();
  const personId = Number(params?.id || 0);

  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [activity, setActivity] = useState<PersonActivity | null>(null);
  const [peopleDirectory, setPeopleDirectory] = useState<DirectoryEntry[]>([]);
  const [suggestedFaces, setSuggestedFaces] = useState<EventFaceEntry[]>([]);
  const [personEventFaces, setPersonEventFaces] = useState<EventFaceEntry[]>(
    [],
  );
  const [status, setStatus] = useState<string>("");
  const [isBusy, setIsBusy] = useState(false);

  const [newAlias, setNewAlias] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [splitNames, setSplitNames] = useState("");
  const [splitKeepAlias, setSplitKeepAlias] = useState(true);

  const [quickMemoryText, setQuickMemoryText] = useState("");
  const [fullMemoryText, setFullMemoryText] = useState("");
  const [fullMemoryDateText, setFullMemoryDateText] = useState("");

  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [birthdayText, setBirthdayText] = useState("");
  const [comprefaceSubjectName, setComprefaceSubjectName] = useState("");
  const [faceImageSizes, setFaceImageSizes] = useState<
    Record<number, FaceImageSize>
  >({});
  const [photoModal, setPhotoModal] = useState<PersonPhotoModalState>({
    isOpen: false,
    assetId: null,
    sourceDownloadPath: null,
    imageUrl: "",
    title: "",
    filename: null,
    capturedText: null,
    positionText: null,
    dimensionsText: null,
    notes: null,
    faces: [],
    focusFaceId: null,
  });

  const mergeTargets = useMemo(
    () => peopleDirectory.filter((entry) => entry.id !== personId),
    [peopleDirectory, personId],
  );

  const allKnownFaces = useMemo(() => {
    const byId = new Map<number, EventFaceEntry>();
    for (const face of personEventFaces) {
      byId.set(face.id, face);
    }
    for (const face of suggestedFaces) {
      byId.set(face.id, face);
    }
    return Array.from(byId.values());
  }, [personEventFaces, suggestedFaces]);

  const facesByAssetDownloadUrl = useMemo(() => {
    const grouped: Record<string, EventFaceEntry[]> = {};
    for (const face of allKnownFaces) {
      if (!grouped[face.asset_download_url]) {
        grouped[face.asset_download_url] = [];
      }
      grouped[face.asset_download_url].push(face);
    }
    return grouped;
  }, [allKnownFaces]);

  async function loadAll() {
    if (!personId || Number.isNaN(personId)) {
      return;
    }

    const [personData, activityData, peopleData, faceData] = await Promise.all([
      fetchPersonDetail(personId),
      fetchPersonActivity(personId),
      fetchPeopleDirectory(),
      fetchPersonSuggestedFaces(personId),
    ]);

    const eventFaceResults = await Promise.allSettled(
      activityData.events.map((event) => fetchEventFaces(event.id)),
    );
    const eventFaces = eventFaceResults
      .filter(
        (result): result is PromiseFulfilledResult<EventFaceEntry[]> =>
          result.status === "fulfilled",
      )
      .flatMap((result) => result.value);

    setPerson(personData);
    setActivity(activityData);
    setPeopleDirectory(peopleData);
    setSuggestedFaces(faceData);
    setPersonEventFaces(eventFaces);

    setRenameValue(personData.name);
    setPhone(personData.contact.phone ?? "");
    setEmail(personData.contact.email ?? "");
    setAddress(personData.contact.address ?? "");
    setNotes(personData.contact.notes ?? "");
    setBirthdayText(personData.contact.birthday_text ?? "");
    setComprefaceSubjectName(
      personData.compreface_subject_id ?? personData.name,
    );
  }

  useEffect(() => {
    loadAll().catch((error) => {
      setStatus(
        error instanceof Error
          ? error.message
          : "Failed to load person details",
      );
    });
  }, [personId]);

  async function runMutation(action: () => Promise<void>, success: string) {
    setIsBusy(true);
    try {
      await action();
      await loadAll();
      setStatus(success);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Action failed");
    } finally {
      setIsBusy(false);
    }
  }

  function onFaceImageLoad(faceId: number, image: HTMLImageElement) {
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    if (!width || !height) {
      return;
    }

    setFaceImageSizes((current) => {
      const existing = current[faceId];
      if (existing && existing.width === width && existing.height === height) {
        return current;
      }
      return {
        ...current,
        [faceId]: { width, height },
      };
    });
  }

  function getFaceOverlayBox(
    face: EventFaceEntry,
  ): { x: number; y: number; w: number; h: number } | null {
    const size = faceImageSizes[face.id];
    if (!size) {
      return null;
    }

    // Backfill compatibility: older/alternate detectors may return normalized [0..1] values.
    const looksNormalized =
      face.bbox_x >= 0 &&
      face.bbox_y >= 0 &&
      face.bbox_w > 0 &&
      face.bbox_h > 0 &&
      face.bbox_x <= 1 &&
      face.bbox_y <= 1 &&
      face.bbox_w <= 1 &&
      face.bbox_h <= 1;

    const x = looksNormalized ? face.bbox_x * size.width : face.bbox_x;
    const y = looksNormalized ? face.bbox_y * size.height : face.bbox_y;
    const w = looksNormalized ? face.bbox_w * size.width : face.bbox_w;
    const h = looksNormalized ? face.bbox_h * size.height : face.bbox_h;

    if (w <= 0 || h <= 0) {
      return null;
    }

    const maxX = Math.max(0, size.width - 1);
    const maxY = Math.max(0, size.height - 1);
    const clampedX = Math.min(Math.max(0, x), maxX);
    const clampedY = Math.min(Math.max(0, y), maxY);
    const clampedW = Math.min(w, size.width - clampedX);
    const clampedH = Math.min(h, size.height - clampedY);

    if (clampedW <= 0 || clampedH <= 0) {
      return null;
    }

    return { x: clampedX, y: clampedY, w: clampedW, h: clampedH };
  }

  function openFaceModal(face: EventFaceEntry) {
    setPhotoModal({
      isOpen: true,
      assetId: face.asset_id,
      sourceDownloadPath: face.asset_download_url,
      imageUrl: resolveApiUrl(`${face.asset_download_url}?download=false`),
      title: face.asset_title || face.compreface_subject || `Face #${face.id}`,
      filename: face.asset_title || null,
      capturedText: null,
      positionText: null,
      dimensionsText: null,
      notes: null,
      faces: facesByAssetDownloadUrl[face.asset_download_url] || [face],
      focusFaceId: face.id,
    });
  }

  function openAssetModal(assetId: number) {
    const asset = (activity?.assets || []).find(
      (entry) => entry.id === assetId,
    );
    if (!asset) {
      return;
    }
    const hasGps = asset.gps_latitude !== null && asset.gps_longitude !== null;
    setPhotoModal({
      isOpen: true,
      assetId: asset.id,
      sourceDownloadPath: asset.download_url,
      imageUrl: resolveApiUrl(`${asset.download_url}?download=false`),
      title: asset.title || asset.original_filename || `Photo #${asset.id}`,
      filename: asset.original_filename,
      capturedText: formatAssetCaptureDate(asset) || null,
      positionText: hasGps
        ? `${asset.gps_latitude!.toFixed(6)}, ${asset.gps_longitude!.toFixed(6)}`
        : null,
      dimensionsText:
        asset.image_width !== null || asset.image_height !== null
          ? `${asset.image_width || "?"} x ${asset.image_height || "?"}`
          : null,
      notes: asset.notes,
      faces: facesByAssetDownloadUrl[asset.download_url] || [],
      focusFaceId: null,
    });
  }

  if (!personId || Number.isNaN(personId)) {
    return (
      <main>
        <p>Invalid person id.</p>
      </main>
    );
  }

  const focusedModalFace = photoModal.focusFaceId
    ? photoModal.faces.find((face) => face.id === photoModal.focusFaceId) ||
      null
    : null;

  const modalTopActions = [
    {
      label: "Analyze Photo",
      variant: "secondary" as const,
      disabled: isBusy || photoModal.assetId === null,
      onClick: () => {
        if (photoModal.assetId === null) {
          return;
        }
        const assetId = photoModal.assetId;
        runMutation(async () => {
          await processSinglePhotoAsset(assetId, true);
        }, "Photo analysis refreshed.");
      },
    },
    ...(focusedModalFace
      ? [
          {
            label: "Approve Face",
            variant: "primary" as const,
            disabled: isBusy,
            onClick: () => {
              runMutation(async () => {
                await approvePersonFace(personId, focusedModalFace.id);
                setPhotoModal((current) => ({ ...current, isOpen: false }));
              }, "Face approved and synced to CompreFace.");
            },
          },
          {
            label: "Disapprove Face",
            variant: "ghost" as const,
            disabled: isBusy,
            onClick: () => {
              runMutation(async () => {
                await deleteFace(focusedModalFace.id);
                setPhotoModal((current) => ({ ...current, isOpen: false }));
              }, "Face suggestion removed.");
            },
          },
        ]
      : []),
  ];

  const modalFooterActions = photoModal.sourceDownloadPath
    ? [
        {
          label: "View",
          variant: "secondary" as const,
          onClick: () => {
            window.open(
              resolveApiUrl(`${photoModal.sourceDownloadPath}?download=false`),
              "_blank",
              "noopener,noreferrer",
            );
          },
        },
        {
          label: "Download",
          variant: "secondary" as const,
          onClick: () => {
            window.open(
              resolveApiUrl(`${photoModal.sourceDownloadPath}?download=true`),
              "_blank",
              "noopener,noreferrer",
            );
          },
        },
      ]
    : [];

  return (
    <main>
      <div className="personDetailsHero">
        <a href="/" className="ghost">
          Back to timeline
        </a>
        <h1>{person?.name ?? "Loading person..."}</h1>
        <p className="meta">
          Manage profile, memories, events, photos, and face approvals.
        </p>
        {status ? <p className="status">{status}</p> : null}
      </div>

      <section className="panel personDetailsGrid">
        <article className="personColumn">
          <h2>Contact Details</h2>
          <label>
            Phone
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone number"
            />
          </label>
          <label>
            Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
            />
          </label>
          <label>
            Address
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Address"
            />
          </label>
          <label>
            Birthday
            <input
              value={birthdayText}
              onChange={(e) => setBirthdayText(e.target.value)}
              placeholder="e.g. 1958-04-22"
            />
          </label>
          <label>
            Notes
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes about this person"
              rows={4}
            />
          </label>
          <button
            className="primary"
            disabled={isBusy}
            onClick={() =>
              runMutation(async () => {
                await updatePersonContact(personId, {
                  phone,
                  email,
                  address,
                  notes,
                  birthday_text: birthdayText,
                });
              }, "Contact details saved.")
            }
          >
            Save Contact Details
          </button>
        </article>

        <article className="personColumn">
          <h2>Identity Actions</h2>
          <label>
            Name
            <input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
            />
          </label>
          <button
            className="secondary"
            disabled={isBusy || !renameValue.trim()}
            onClick={() =>
              runMutation(async () => {
                await renameDirectoryEntry(
                  "people",
                  personId,
                  renameValue.trim(),
                );
              }, "Name updated.")
            }
          >
            Rename
          </button>

          <div className="personInlineRow">
            <input
              value={newAlias}
              onChange={(e) => setNewAlias(e.target.value)}
              placeholder="Add alias"
            />
            <button
              className="secondary"
              disabled={isBusy || !newAlias.trim()}
              onClick={() =>
                runMutation(async () => {
                  await addPersonAlias(personId, newAlias.trim());
                  setNewAlias("");
                }, "Alias added.")
              }
            >
              Add Alias
            </button>
          </div>

          <div className="aliasList">
            {(person?.aliases ?? []).map((alias) => (
              <span key={alias} className="aliasChip">
                {alias}
                <button
                  className="aliasRemove"
                  disabled={isBusy}
                  onClick={() =>
                    runMutation(async () => {
                      await removePersonAlias(personId, alias);
                    }, "Alias removed.")
                  }
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <label>
            CompreFace subject
            <input
              value={comprefaceSubjectName}
              onChange={(e) => setComprefaceSubjectName(e.target.value)}
              placeholder="Subject name"
            />
          </label>
          <button
            className="secondary"
            disabled={isBusy || !comprefaceSubjectName.trim()}
            onClick={() =>
              runMutation(async () => {
                await linkPersonToCompreface(
                  personId,
                  comprefaceSubjectName.trim(),
                );
              }, "CompreFace link updated.")
            }
          >
            Link CompreFace Subject
          </button>

          <label>
            Merge into
            <select
              value={mergeTargetId}
              onChange={(e) => setMergeTargetId(e.target.value)}
            >
              <option value="">Select person</option>
              {mergeTargets.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            disabled={isBusy || !mergeTargetId}
            onClick={() =>
              runMutation(async () => {
                await mergePeopleEntries(personId, Number(mergeTargetId));
                window.location.href = `/people/${mergeTargetId}`;
              }, "People merged.")
            }
          >
            Merge Person
          </button>

          <label>
            Split into (comma-separated names)
            <input
              value={splitNames}
              onChange={(e) => setSplitNames(e.target.value)}
            />
          </label>
          <label className="personCheckboxRow">
            <input
              type="checkbox"
              checked={splitKeepAlias}
              onChange={(e) => setSplitKeepAlias(e.target.checked)}
            />
            Keep current name as alias on new people
          </label>
          <button
            className="secondary"
            disabled={isBusy || !splitNames.trim()}
            onClick={() =>
              runMutation(async () => {
                const names = splitNames
                  .split(",")
                  .map((n) => n.trim())
                  .filter(Boolean);
                await splitPersonEntry(personId, names, splitKeepAlias);
                window.location.href = "/";
              }, "Person split.")
            }
          >
            Split Person
          </button>

          <button
            className="ghost"
            disabled={isBusy}
            onClick={() =>
              runMutation(async () => {
                await deleteDirectoryEntry("people", personId);
                window.location.href = "/";
              }, "Person deleted.")
            }
          >
            Delete Person
          </button>
        </article>
      </section>

      <section className="panel personSection">
        <h2>Memories</h2>
        <div className="personInlineRow">
          <input
            value={quickMemoryText}
            onChange={(e) => setQuickMemoryText(e.target.value)}
            placeholder="Quick memory note"
          />
          <button
            className="secondary"
            disabled={isBusy || !quickMemoryText.trim()}
            onClick={() =>
              runMutation(async () => {
                await createPersonQuickMemory(personId, {
                  text: quickMemoryText.trim(),
                });
                setQuickMemoryText("");
              }, "Quick memory added.")
            }
          >
            Add Quick Memory
          </button>
        </div>

        <div className="personFullMemoryForm">
          <textarea
            value={fullMemoryText}
            onChange={(e) => setFullMemoryText(e.target.value)}
            placeholder="Full memory about this person"
            rows={4}
          />
          <input
            value={fullMemoryDateText}
            onChange={(e) => setFullMemoryDateText(e.target.value)}
            placeholder="Optional date text"
          />
          <button
            className="secondary"
            disabled={isBusy || !fullMemoryText.trim()}
            onClick={() =>
              runMutation(async () => {
                await createPersonQuickMemory(personId, {
                  text: fullMemoryText.trim(),
                  estimated_date_text: fullMemoryDateText.trim() || null,
                });
                setFullMemoryText("");
                setFullMemoryDateText("");
              }, "Memory saved.")
            }
          >
            Save Full Memory
          </button>
        </div>

        <div className="personSimpleList">
          {(activity?.memories ?? []).map((memory) => (
            <div key={memory.id} className="personListCard">
              <strong>{memory.event_description || "Untitled memory"}</strong>
              <p>{memory.transcript}</p>
            </div>
          ))}
          {activity && activity.memories.length === 0 ? (
            <p className="meta">No memories linked yet.</p>
          ) : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Events</h2>
        <div className="personSimpleList">
          {(activity?.events ?? []).map((event) => (
            <div key={event.id} className="personListCard">
              <strong>{event.title}</strong>
              <p>{event.event_date_text || "No event date"}</p>
              <p>{event.description || ""}</p>
            </div>
          ))}
          {activity && activity.events.length === 0 ? (
            <p className="meta">No events linked yet.</p>
          ) : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Pictures</h2>
        <div className="personAssetGrid">
          {(activity?.assets ?? []).map((asset) => (
            <figure key={asset.id} className="personAssetCard">
              <button
                type="button"
                className="personAssetImageButton"
                onClick={() => openAssetModal(asset.id)}
                title="Open full photo details"
              >
                <img
                  src={resolveApiUrl(`${asset.download_url}?download=false`)}
                  alt={asset.title ?? "Linked photo"}
                />
              </button>
              <figcaption>
                {asset.title || asset.original_filename || `Photo #${asset.id}`}
              </figcaption>
            </figure>
          ))}
          {activity && activity.assets.length === 0 ? (
            <p className="meta">No photos linked yet.</p>
          ) : null}
        </div>
      </section>

      <section className="panel personSection">
        <h2>Face Approvals</h2>
        <div className="personFaceTableWrap">
          <table className="personFaceTable">
            <thead>
              <tr>
                <th>Preview</th>
                <th>Suggested Subject</th>
                <th>Similarity</th>
                <th>Confidence</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {suggestedFaces.map((face) => (
                <tr key={face.id}>
                  <td>
                    <button
                      type="button"
                      className="personFacePreviewFrame personFacePreviewButton"
                      onClick={() => openFaceModal(face)}
                      title="Open larger photo and face details"
                    >
                      <img
                        className="personFacePreview"
                        src={resolveApiUrl(
                          `${face.asset_download_url}?download=false`,
                        )}
                        alt="Suggested face"
                        onLoad={(event) =>
                          onFaceImageLoad(face.id, event.currentTarget)
                        }
                      />
                      {(() => {
                        const box = getFaceOverlayBox(face);
                        const size = faceImageSizes[face.id];
                        if (!box || !size) {
                          return null;
                        }
                        return (
                          <svg
                            className="personFaceOverlay"
                            viewBox={`0 0 ${size.width} ${size.height}`}
                            aria-hidden="true"
                          >
                            <rect
                              x={box.x}
                              y={box.y}
                              width={box.w}
                              height={box.h}
                              className="personFaceOverlayBox personFaceOverlayBoxStrong"
                            />
                          </svg>
                        );
                      })()}
                    </button>
                  </td>
                  <td>
                    <strong>{face.compreface_subject || "Unknown"}</strong>
                  </td>
                  <td>
                    {typeof face.compreface_similarity === "number"
                      ? `${Math.round(face.compreface_similarity * 100)}%`
                      : "n/a"}
                  </td>
                  <td>
                    {typeof face.confidence === "number"
                      ? `${Math.round(face.confidence * 100)}%`
                      : "n/a"}
                  </td>
                  <td>
                    <button
                      className="secondary"
                      disabled={isBusy}
                      onClick={() =>
                        runMutation(async () => {
                          await approvePersonFace(personId, face.id);
                        }, "Face approved and synced to CompreFace.")
                      }
                    >
                      Approve Face
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {suggestedFaces.length === 0 ? (
            <p className="meta">No pending suggested faces.</p>
          ) : null}
        </div>
      </section>

      <PhotoDetailsModal
        isOpen={photoModal.isOpen}
        imageUrl={photoModal.imageUrl}
        title={photoModal.title}
        onClose={() =>
          setPhotoModal((current) => ({ ...current, isOpen: false }))
        }
        faces={photoModal.faces}
        focusFaceId={photoModal.focusFaceId}
        filename={photoModal.filename}
        capturedText={photoModal.capturedText}
        positionText={photoModal.positionText}
        dimensionsText={photoModal.dimensionsText}
        notes={photoModal.notes}
        topActions={modalTopActions}
        footerActions={modalFooterActions}
      />
    </main>
  );
}
