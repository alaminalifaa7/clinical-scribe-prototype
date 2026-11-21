
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Mic,
  Pause,
  Play,
  Square,
  FileText,
  AudioLines,
  Check,
  X,
  Pencil,
  AlertTriangle,
  Activity,
  ClipboardList,
  RotateCcw,
  Save
} from "lucide-react";
import "./style.css";

const API = "http://localhost:8000/api";

function App() {
  const [tab, setTab] = useState("transcript");
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [status, setStatus] = useState("Ready to record");
  const [analysis, setAnalysis] = useState(null);
  const [busy, setBusy] = useState(false);
  const [language, setLanguage] = useState("auto");
  const [sessionId] = useState(() => crypto.randomUUID());

  const [health, setHealth] = useState(null);
  const [soap, setSoap] = useState({
    subjective: "",
    objective: "",
    assessment: "",
    plan: ""
  });
  const [clarificationResponses, setClarificationResponses] = useState({});

  const recorder = useRef(null);
  const stream = useRef(null);
  const chunks = useRef([]);

  useEffect(() => {
    fetch(API + "/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ ok: false }));
  }, []);

  // Upload the complete recording once, after MediaRecorder stops.
  async function uploadRecording(blob, selectedLanguage) {
    if (!blob || blob.size === 0) {
      setStatus("No audio was captured. Please check your microphone and try again.");
      return;
    }

    setBusy(true);
    setStatus(`Uploading recording (${(blob.size / 1024).toFixed(1)} KB) to ElevenLabs...`);

    try {
      const fd = new FormData();
      fd.append("file", blob, "consultation.webm");

      const url = new URL(API + "/transcribe");
      url.searchParams.set("language", selectedLanguage);

      console.info("Uploading complete recording:", {
        size: blob.size,
        type: blob.type,
        language: selectedLanguage
      });

      const response = await fetch(url, {
        method: "POST",
        body: fd
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = await response.json();
      console.info("Transcription response:", data);

      const text = typeof data.text === "string" ? data.text.trim() : "";

      if (!text) {
        setTranscript("");
        setStatus(
          "ElevenLabs received the recording but returned no transcript. Check the recording audio and microphone input."
        );
        return;
      }

      setTranscript(text);
      setStatus("Transcription complete. Review the transcript before structuring the note.");
    } catch (error) {
      console.error("Transcription failed:", error);
      setStatus("Transcription error: " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({
        audio: true
      });

      stream.current = audioStream;
      chunks.current = [];

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const mediaRecorder = new MediaRecorder(audioStream, {
        mimeType
      });

      recorder.current = mediaRecorder;

      // Collect chunks only. Do not upload partial WebM files.
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.current.push(event.data);

          console.info("Audio chunk captured:", {
            size: event.data.size,
            totalChunks: chunks.current.length
          });
        }
      };

      mediaRecorder.onstop = async () => {
        // The final dataavailable event is delivered before this stop event.
        const completeRecording = new Blob(chunks.current, {
          type: mediaRecorder.mimeType || mimeType
        });

        console.info("Recording finished:", {
          chunks: chunks.current.length,
          totalBytes: completeRecording.size,
          mimeType: completeRecording.type
        });

        // Release the microphone.
        if (stream.current) {
          stream.current.getTracks().forEach((track) => track.stop());
          stream.current = null;
        }

        setRecording(false);
        setPaused(false);

        // Upload exactly once after recording has finished.
        await uploadRecording(completeRecording, language);

        chunks.current = [];
      };

      mediaRecorder.start(1000);

      setRecording(true);
      setPaused(false);
      setTranscript("");
      setAnalysis(null);
      setClarificationResponses({});
      setStatus("Recording in progress...");
    } catch (error) {
      console.error("Microphone error:", error);
      setStatus("Microphone access failed: " + error.message);
    }
  }

  function pause() {
    if (recorder.current?.state === "recording") {
      recorder.current.pause();
      setPaused(true);
      setStatus("Recording paused");
    }
  }

  function resume() {
    if (recorder.current?.state === "paused") {
      recorder.current.resume();
      setPaused(false);
      setStatus("Recording resumed");
    }
  }

  function stop() {
    if (recorder.current && recorder.current.state !== "inactive") {
      setStatus("Stopping recording and preparing audio...");
      recorder.current.stop();
    }
  }

  async function analyze() {
    if (!transcript.trim()) return;

    setBusy(true);
    setStatus("Sending transcript to local LLM...");

    try {
      const response = await fetch(API + "/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          transcript,
          language
        })
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = await response.json();

      setAnalysis(data);
      setSoap(data.soap || {});
      setTab("review");
      setStatus("Structured draft ready for clinician review.");
    } catch (error) {
      setStatus("Analysis failed: " + error.message);
    } finally {
      setBusy(false);
    }
  }

  async function log(action, fact, revised) {
    try {
      await fetch(API + "/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          session_id: sessionId,
          fact_id: fact?.id,
          action,
          original_value: fact?.value,
          revised_value: revised,
          note: "Clinician review prototype"
        })
      });
    } catch (error) {
      console.error("Feedback logging failed:", error);
    }
  }

  function updateFact(id, patch) {
    setAnalysis((current) => ({
      ...current,
      facts: current.facts.map((fact) =>
        fact.id === id ? { ...fact, ...patch } : fact
      )
    }));
  }

  function editFact(fact) {
    const value = prompt("Edit extracted value", fact.value);

    if (value !== null) {
      updateFact(fact.id, {
        value,
        status: "edited"
      });

      log("edit", fact, value);
    }
  }

  async function saveSoap() {
    await log("soap_note_saved", null, JSON.stringify(soap));
    setStatus("SOAP draft saved to local feedback log.");
  }

  const facts = analysis?.facts || [];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandIcon">
            <Activity size={21} />
          </div>
          <div>
            <b>Clinical Scribe</b>
            <small>Research workspace</small>
          </div>
        </div>

        <div className="sideLabel">WORKSPACE</div>
        <button className="sideActive">
          <ClipboardList size={17} /> Consultation
        </button>

        <div className="sideLabel">RESEARCH MODE</div>
        <div className="sideNote">
          Local-first prototype
          <br />
          No cloud AI calls
        </div>

        <div className="sideBottom">
          <span className={`dot ${health?.ok ? "green" : "red"}`}></span>
          {health?.ok
            ? health.demo_mode
              ? "Demo mode"
              : "Backend connected"
            : "Backend offline"}
          <small>Research use only</small>
        </div>
      </aside>

      <main className="main">
        <header>
          <div>
            <div className="eyebrow">CONSULTATION WORKSPACE</div>
            <h1>New consultation</h1>
            <p>
              Capture a conversation, structure the information and review the
              draft.
            </p>
          </div>

          <div className="headerRight">
            <span className="privacy">
              <span className="dot green"></span> Local processing
            </span>
            <span className="avatar">DR</span>
          </div>
        </header>

        <div className="notice">
          <AlertTriangle size={16} />
          Research prototype only. Do not use with real patient data or for
          clinical decisions.
        </div>

        <section className="recordCard">
          <div className="recordTop">
            <div>
              <div className="eyebrow">AUDIO CAPTURE</div>
              <h2>Consultation recording</h2>
              <p>Record in Bangla, English or a mix of both.</p>
            </div>

            <div className="selectWrap">
              <label>Language</label>
              <select
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                disabled={recording}
              >
                <option value="auto">Auto detect</option>
                <option value="bn">Bangla</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>

          <div className="recControls">
            <div className={`micOrb ${recording && !paused ? "live" : ""}`}>
              <Mic size={25} />
            </div>

            <div className="recStatus">
              <b>
                {recording
                  ? paused
                    ? "Recording paused"
                    : "Recording in progress"
                  : status}
              </b>
              <small>
                {recording
                  ? "Audio is being captured. The complete recording will be transcribed when you press Stop."
                  : "Start a recording to capture the conversation. Transcription begins after you stop."}
              </small>
            </div>

            <div className="buttons">
              {!recording ? (
                <button
                  className="primary"
                  onClick={start}
                  disabled={busy}
                >
                  <Mic size={16} /> Start recording
                </button>
              ) : (
                <>
                  {!paused ? (
                    <button className="secondary" onClick={pause}>
                      <Pause size={16} /> Pause
                    </button>
                  ) : (
                    <button className="secondary" onClick={resume}>
                      <Play size={16} /> Resume
                    </button>
                  )}

                  <button className="stop" onClick={stop}>
                    <Square size={15} /> Stop
                  </button>
                </>
              )}
            </div>
          </div>
        </section>

        <div className="tabs">
          <button
            className={tab === "transcript" ? "tab active" : "tab"}
            onClick={() => setTab("transcript")}
          >
            <AudioLines size={16} /> Transcript
            <span className="count">
              {transcript ? transcript.trim().split(/\s+/).length : 0} words
            </span>
          </button>

          <button
            className={tab === "review" ? "tab active" : "tab"}
            onClick={() => setTab("review")}
          >
            <FileText size={16} /> Structured note
            {analysis && <span className="count">{facts.length} facts</span>}
          </button>
        </div>

        {tab === "transcript" ? (
          <section className="panel">
            <div className="panelHead">
              <div>
                <h3>Conversation transcript</h3>
                <p>
                  The complete transcript appears here after recording stops.
                </p>
              </div>

              <button
                className="ghost"
                onClick={() => {
                  setTranscript("");
                  setAnalysis(null);
                  setStatus("Transcript cleared");
                }}
              >
                <RotateCcw size={15} /> Clear
              </button>
            </div>

            <div className="transcriptBox">
              {transcript ? (
                <div className="transcriptText">{transcript}</div>
              ) : (
                <div className="empty">
                  <AudioLines size={30} />
                  <b>No transcript yet</b>
                  <span>
                    Start recording, stop when finished, and the transcript
                    will appear here.
                  </span>
                </div>
              )}
            </div>

            <div className="panelFoot">
              <span>{status}</span>
              <button
                className="primary"
                disabled={!transcript.trim() || recording || busy}
                onClick={analyze}
              >
                {busy ? "Processing..." : "Generate structured draft"}
                <span>→</span>
              </button>
            </div>
          </section>
        ) : (
          <section className="panel">
            <div className="panelHead">
              <div>
                <h3>Clinician review</h3>
                <p>
                  Review extracted facts, clarify uncertainty and edit the
                  draft SOAP note.
                </p>
              </div>

              <button className="ghost" onClick={() => setTab("transcript")}>
                View transcript
              </button>
            </div>

            {!analysis ? (
              <div className="empty large">
                <FileText size={32} />
                <b>No structured draft yet</b>
                <span>
                  Finish recording, open Transcript and select Generate
                  structured draft.
                </span>
              </div>
            ) : (
              <>
                <div className="reviewGrid">
                  <div className="factsCol">
                    <div className="sectionTitle">
                      <h4>Extracted information</h4>
                      <span>{facts.length} items</span>
                    </div>

                    {facts.map((fact) => (
                      <div className="fact" key={fact.id}>
                        <div className="factTop">
                          <span className="factCat">
                            {fact.category?.replaceAll("_", " ")}
                          </span>
                          <span className={`confidence ${fact.confidence}`}>
                            {fact.confidence} confidence
                          </span>
                        </div>

                        <div className="factValue">
                          {fact.field}: <b>{fact.value}</b>
                        </div>

                        <div className="evidence">
                          “{fact.evidence_quote}”
                        </div>

                        {fact.uncertainty_reason && (
                          <div className="uncertain">
                            <AlertTriangle size={13} />
                            {fact.uncertainty_reason}
                          </div>
                        )}

                        <div className="factActions">
                          <button
                            onClick={() => {
                              updateFact(fact.id, { status: "accepted" });
                              log("accept", fact, fact.value);
                            }}
                          >
                            <Check size={14} /> Accept
                          </button>

                          <button
                            onClick={() => {
                              updateFact(fact.id, { status: "rejected" });
                              log("reject", fact);
                            }}
                          >
                            <X size={14} /> Reject
                          </button>

                          <button onClick={() => editFact(fact)}>
                            <Pencil size={14} /> Edit
                          </button>

                          <span className="factState">
                            {fact.status === "accepted"
                              ? "Accepted"
                              : fact.status === "rejected"
                              ? "Rejected"
                              : fact.status === "edited"
                              ? "Edited"
                              : ""}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="soapCol">
                    <div className="sectionTitle">
                      <h4>Draft SOAP note</h4>
                      <span>Editable</span>
                    </div>

                    {["subjective", "objective", "assessment", "plan"].map(
                      (key) => (
                        <label className="soapField" key={key}>
                          <span>{key.toUpperCase()}</span>
                          <textarea
                            value={soap[key] || ""}
                            onChange={(event) =>
                              setSoap((current) => ({
                                ...current,
                                [key]: event.target.value
                              }))
                            }
                            rows={key === "subjective" ? 5 : 3}
                          />
                        </label>
                      )
                    )}

                    <button className="primary full" onClick={saveSoap}>
                      <Save size={15} /> Save reviewed draft
                    </button>
                  </div>
                </div>

                {!!analysis.clarifications?.length && (
                  <div className="subPanel">
                    <h4>
                      <AlertTriangle size={16} /> Clarification needed
                    </h4>

                    {analysis.clarifications.map((item, index) => (
                      <div className="clarify" key={index}>
                        <b>{item.question}</b>
                        <p>{item.reason}</p>

                        <div className="clarifyInput">
                          <input
                            value={clarificationResponses[index] || ""}
                            onChange={(event) =>
                              setClarificationResponses((current) => ({
                                ...current,
                                [index]: event.target.value
                              }))
                            }
                            placeholder="Record the doctor's clarification..."
                          />

                          <button
                            onClick={() =>
                              log(
                                "clarification",
                                null,
                                clarificationResponses[index] || ""
                              )
                            }
                          >
                            Save clarification
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!!analysis.possible_contradictions?.length && (
                  <div className="subPanel">
                    <h4>Possible contradictions</h4>

                    {analysis.possible_contradictions.map((item, index) => (
                      <div className="clarify" key={index}>
                        {item.description}
                        <p>{(item.evidence_quotes || []).join(" / ")}</p>
                      </div>
                    ))}
                  </div>
                )}

                {!!analysis.missing_information?.length && (
                  <div className="subPanel">
                    <h4>Information not captured</h4>
                    <ul>
                      {analysis.missing_information.map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        <footer>
          Local research prototype · Audio and LLM processing stay on this
          machine when configured as documented.
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
