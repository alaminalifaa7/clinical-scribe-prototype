# Clinical Scribe
### A Research Prototype for Evidence-Grounded Clinical Fact Extraction

Clinical Scribe is a research prototype exploring how clinical information can be extracted from doctor–patient conversations and converted into structured, reviewable clinical notes.

The project focuses on a specific challenge: **how can an AI system extract reliable clinical facts from multilingual conversations while preserving the evidence behind each fact and recognising uncertainty?**

The prototype supports English, Bangla, and Bangla-English code-switched conversations. It combines speech recognition, local language-model-based extraction, evidence-linked facts, and human review in one workflow.

> **Research and demonstration software only. Not for real patient care.**
>
> Do not record identifiable patient data. Generated clinical information is an unverified draft, not a diagnosis or medical advice. All outputs require independent human review.

---

## 1. Research Motivation

Clinical conversations contain much more than symptoms. They include medication names and dosages, allergies, negative symptoms, historical information, patient-reported experiences, clinician observations, and proposed actions.

Converting these conversations into structured notes introduces several challenges:

- **Multilingual speech:** Conversations may switch between Bangla and English, sometimes within a single sentence.
- **Transcription uncertainty:** Speech recognition can misinterpret medical terms, numbers, medication names, and negation.
- **Clinical context:** The same statement can have different meanings depending on its speaker, timing, and context.
- **Unsupported assertions:** A language model may produce plausible clinical information that was never actually stated.
- **Uncertainty:** Some information is ambiguous, incomplete, or contradictory and should not be silently resolved.
- **Human oversight:** Clinicians need to inspect, correct, and reject extracted information before it becomes part of a clinical record.

The project investigates an evidence-grounded approach to clinical fact extraction, where extracted information must remain traceable to the original conversation.

Rather than treating the generated SOAP note as the final output, the prototype makes the intermediate facts, supporting evidence, confidence, and uncertainty visible for review.

### Research direction

**Evidence-Grounded Clinical Fact Extraction under Bangla-English Code-Switching and Transcription Uncertainty**

The broader research question is:

*Can evidence-constrained extraction and explicit uncertainty handling reduce unsupported clinical assertions and improve the reliability of structured clinical notes generated from multilingual conversations?*

This prototype is an initial experimental platform for investigating that question. It does not yet establish that the proposed approach improves clinical accuracy.

---

## 2. Current System Architecture

The system separates speech recognition from clinical information extraction.

| Component | Technology | Responsibility |
|---|---|---|
| Frontend | React, Vite | Recording, transcript display, fact review, SOAP editing |
| Audio capture | Browser MediaRecorder API | Captures consultation audio |
| Speech recognition | ElevenLabs Scribe v3 | Transcribes English, Bangla and multilingual speech |
| Backend | Python, FastAPI | Coordinates transcription and analysis requests |
| Clinical extraction | Ollama with Qwen3 8B | Extracts structured facts and generates draft SOAP notes |
| Feedback storage | Local JSONL file | Records review decisions for later evaluation |

### Processing workflow

1. **Audio capture:** The browser records a consultation using the microphone. Users can start, pause, resume, and stop recording.
2. **Audio submission:** Audio chunks are accumulated in the browser and combined into one complete WebM recording when the user presses Stop.
3. **Speech recognition:** The complete recording is sent to the ElevenLabs Speech-to-Text API using Scribe v3.
4. **Transcript review:** The returned transcript is displayed in the application.
5. **Clinical extraction:** The user initiates analysis. The transcript is sent to the local Ollama model for structured fact extraction and SOAP note generation.
6. **Human review:** Extracted facts, evidence quotes, uncertainty, and the draft SOAP note are presented for inspection and editing.
7. **Feedback logging:** Accept, reject, edit, and note-saving actions are recorded locally for future offline evaluation.

### Architecture overview

```text
        Doctor–Patient Conversation
                    |
                    v
          Browser Audio Capture
          (MediaRecorder API)
                    |
                    v
           Complete WebM Audio
                    |
                    v
        ElevenLabs Scribe v3 API
            (Speech Recognition)
                    |
                    v
             Transcription
                    |
                    v
           Transcript Display
                    |
             User initiates
               analysis
                    |
                    v
          FastAPI Backend
                    |
                    v
          Local Ollama Model
               Qwen3 8B
                    |
                    v
          Structured Fact Extraction
                    |
          +---------+----------+
          |         |          |
          v         v          v
       Evidence  Uncertainty  SOAP Draft
          |         |          |
          +---------+----------+
                    |
                    v
             Human Review
                    |
                    v
          Accept / Reject / Edit
                    |
                    v
           Local JSONL Feedback
```

### Important architectural distinction

The prototype is **local-first for clinical analysis, but not fully local**.

- Audio is transmitted to ElevenLabs for speech recognition.
- The resulting transcript is processed by Ollama running locally.
- Review feedback is stored locally.
- No online model training or automatic learning from feedback is implemented.

This distinction matters when evaluating privacy, reproducibility, and deployment requirements.

---

## 3. Current Features

### Audio recording and transcription

- Browser microphone capture.
- Start, pause, resume, and stop controls.
- Complete recording is uploaded once after recording stops.
- ElevenLabs Scribe v3 handles multilingual transcription.
- Supports English, Bangla, and code-switched conversations.
- Transcript is displayed in the application after processing.

The current implementation uses batch transcription rather than real-time streaming.

### Evidence-linked clinical fact extraction

The local language model extracts structured clinical information from the transcript.

Each extracted fact can include:

- Speaker
- Category
- Field
- Extracted value
- Supporting evidence quote
- Confidence level
- Uncertainty information
- Review status

The intended design is to keep extracted facts connected to the conversation rather than presenting unsupported model-generated statements as established information.

### Structured clinical note generation

The application generates an editable draft SOAP note:

- **Subjective:** Patient-reported symptoms and history.
- **Objective:** Observations and measurements stated in the conversation.
- **Assessment:** Assessment information explicitly supported by the conversation.
- **Plan:** Proposed investigations, treatment instructions, and follow-up information.

The note is a draft for review, not an independently validated clinical document.

### Human-in-the-loop review

The review interface allows the user to:

- Accept extracted facts.
- Reject extracted facts.
- Edit extracted values.
- Inspect supporting evidence.
- Review uncertainty and clarification questions.
- Inspect possible contradictions.
- Edit the generated SOAP note.
- Save reviewed note information.

### Feedback logging

Review actions are stored in a local JSONL feedback log.

This creates a record of human corrections and decisions that can later support:

- Error analysis.
- Extraction evaluation.
- Comparison of model configurations.
- Analysis of recurring transcription and extraction failures.

**The feedback log does not train or update the model automatically.**

---

## 4. Technology and Model Configuration

### Speech recognition: ElevenLabs Scribe v3

The prototype uses ElevenLabs Scribe v3 for batch speech recognition.

It was selected after testing multilingual transcription quality, particularly for Bangla and English speech.

Current configuration:

- Model: `scribe_v3`
- Primary language: Automatic detection by default.
- Optional language selection: Bangla or English.
- Secondary languages: English and Bangla when using automatic or language-specific configuration.
- Audio format: Browser-recorded WebM/Opus.
- Transcription mode: Batch processing after recording stops.

The application sends the complete recording rather than repeatedly submitting partial recordings.

**Research limitation:** A transcript can be fluent and still contain recognition errors. In particular, a clearly transcribed but incorrect medication name, number, or negation may not be detectable through transcript-only evidence checking.

### Clinical language model: Ollama Qwen3 8B

Ollama runs the clinical analysis model locally.

Current model:

```bash
ollama pull qwen3:8b
```

The model is responsible for:

- Extracting atomic clinical facts.
- Associating facts with supporting transcript evidence.
- Producing structured output.
- Generating a draft SOAP note.
- Identifying possible ambiguity and contradictions.

The model does not perform speech recognition.

The configured model can be changed through the backend environment configuration, using `OLLAMA_MODEL`.

### Why separate ASR and LLM?

Separating transcription from clinical analysis makes it possible to investigate errors at different stages.

For example:

1. Did speech recognition correctly capture what was said?
2. Did fact extraction preserve the meaning of the transcript?
3. Did the system associate the correct supporting evidence with the extracted fact?
4. Did it preserve polarity, speaker, and temporality?
5. Did it recognise when the available evidence was insufficient?

These are different failure types and should be evaluated separately.

---

## 5. Research Questions and Planned Evaluation

The prototype provides an initial environment for investigating the following questions.

| Research question | What to investigate |
|---|---|
| RQ1: How does multilingual transcription quality affect clinical fact extraction? | Compare transcription and extraction performance across English, Bangla, and code-switched conversations. |
| RQ2: Can evidence-linked extraction reduce unsupported clinical assertions? | Compare direct extraction with extraction that requires supporting transcript evidence. |
| RQ3: Can explicit uncertainty handling improve reliability? | Evaluate when the system should accept, reject, or abstain from extracting a fact. |
| RQ4: Which clinical information is most vulnerable to errors? | Analyse medication identity, dosage, negation, temporality, speaker attribution, and other clinical attributes. |
| RQ5: How effectively can human review resolve extraction errors? | Measure correction rates, review decisions, and the types of errors that require intervention. |

### Proposed evaluation metrics

The following metrics are planned for future experiments. They are not yet established results.

**Speech recognition**
- Word error rate (WER).
- Character error rate (CER).
- Bangla-specific and code-switching error analysis.
- Medication and number transcription accuracy.

**Clinical fact extraction**
- Precision, recall, and F1.
- Attribute-level accuracy.
- Speaker attribution accuracy.
- Negation and temporality accuracy.
- Medication name, dose, and frequency accuracy.

**Evidence and uncertainty**
- Evidence support rate.
- Unsupported assertion rate.
- Evidence-span correctness.
- Abstention quality.
- Risk–coverage analysis.

**Human review**
- Acceptance and rejection rates.
- Correction frequency.
- Correction types.
- Error resolution rate.

### Important research distinction

Evidence grounding and transcription accuracy are not the same thing.

If the speech recogniser incorrectly converts a spoken negative statement into a clear but incorrect positive statement, a downstream extraction system may quote that transcript accurately while still representing the original conversation incorrectly.

For this reason, future evaluation should distinguish:

1. Errors introduced during speech recognition.
2. Errors introduced during clinical fact extraction.
3. Errors introduced during evidence association.
4. Errors that remain unresolved because the system lacks sufficient information.

---

## 6. Running the Prototype

### Prerequisites

Install the following:

- Python 3.9 or newer.
- Node.js and npm.
- Ollama.
- An ElevenLabs account and API key with access to speech-to-text.

Useful installation links:

- [Python](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/)
- [Ollama](https://ollama.com/download)
- [ElevenLabs](https://elevenlabs.io/)

### Step 1: Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd clinical-scribe-prototype
```

### Step 2: Start Ollama

Install Ollama and download the model:

```bash
ollama pull qwen3:8b
```

Ensure Ollama is running. Its default local API endpoint is:

```text
http://localhost:11434
```

You can check the installed model with:

```bash
ollama list
```

### Step 3: Configure the backend

Open a terminal:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Configure the required environment variables in `backend/.env`:

```env
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_STT_MODEL=scribe_v3
OLLAMA_MODEL=qwen3:8b
```

Keep any other existing environment variables from `.env.example`.

**Security:** Never commit `.env` or expose your ElevenLabs API key in frontend code, screenshots, public repositories, or logs.

Start the backend:

```bash
uvicorn app:app --reload --port 8000
```

The backend should be available at:

```text
http://localhost:8000
```

Check its health endpoint:

```text
http://localhost:8000/api/health
```

### Step 4: Start the frontend

Open a second terminal:

```bash
cd clinical-scribe-prototype/frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the application:

```text
http://localhost:5173
```

Allow microphone access when prompted.

### Step 5: Run a consultation test

1. Open the application.
2. Select Auto detect, Bangla, or English.
3. Press Start recording.
4. Speak a short consultation in the selected language.
5. Use Pause and Resume if required.
6. Press Stop.
7. Wait for ElevenLabs to return the transcript.
8. Inspect the transcript.
9. Select **Generate structured draft**.
10. Review extracted facts, supporting evidence, uncertainty, and the SOAP note.
11. Accept, reject, or edit facts as appropriate.

The application does not automatically generate the structured note immediately after recording. The user initiates clinical analysis after transcription.

---

## 7. Current Implementation Scope and Limitations

This is an early research prototype, not a production clinical documentation system.

| Area | Current status |
|---|---|
| Audio capture | Implemented |
| Pause and resume | Implemented |
| Batch transcription | Implemented using ElevenLabs Scribe v3 |
| Bangla and English support | Implemented through multilingual transcription configuration |
| Code-switching | Supported, but not independently benchmarked |
| Local clinical analysis | Implemented using Ollama Qwen3 8B |
| Structured fact extraction | Implemented |
| Evidence quotes | Implemented |
| Confidence and uncertainty fields | Implemented |
| Draft SOAP generation | Implemented |
| Human review | Implemented |
| Local feedback logging | Implemented |
| Automatic model training | Not implemented |
| True real-time transcription | Not implemented |
| Clinical validation | Not performed |
| Benchmark evaluation | Planned |
| Independent evidence verification | Further research and validation required |

### Known limitations

**1. External speech recognition**

Audio is transmitted to ElevenLabs. Therefore, the current system is not fully offline or fully local.

**2. Batch rather than streaming transcription**

The complete recording is submitted after Stop. The prototype does not currently provide live transcription during a consultation.

**3. Transcription errors**

Speech recognition can misinterpret medication names, numbers, clinical terminology, and negation. Downstream language-model processing cannot reliably recover information that was incorrectly transcribed.

**4. Evidence quotes are not proof of correctness**

A generated evidence quote may accurately match an incorrect transcript. Evidence association must be evaluated separately from the accuracy of the original audio transcription.

**5. Model-generated confidence is not calibrated**

Confidence values generated by the language model should not be treated as statistically calibrated probabilities.

**6. No clinical validation**

The system has not been validated for clinical use, diagnostic accuracy, patient safety, or regulatory compliance.

**7. Feedback is not online learning**

Human review decisions are saved for later research analysis. They do not automatically update the model.

---

## 8. Future Research and Development

The next stage is to move from a working demonstration towards a controlled experimental system.

### Phase 1 — Establish a transcription benchmark

- Develop a small, carefully reviewed English, Bangla, and code-switched conversation dataset.
- Compare transcription outputs against manually verified transcripts.
- Identify errors involving medication names, numbers, negation, and clinical terminology.
- Separate ASR errors from downstream extraction errors.

### Phase 2 — Investigate evidence-constrained extraction

Compare different extraction approaches:

1. Direct clinical fact extraction.
2. Evidence-linked fact extraction.
3. Evidence-constrained extraction with attribute validation and abstention.

Investigate whether requiring evidence and validating attributes can reduce unsupported assertions.

### Phase 3 — Evaluate uncertainty and abstention

Investigate whether the system can recognise when evidence is insufficient.

Focus on:

- Contradictory statements.
- Unclear medication information.
- Missing dosages or frequencies.
- Ambiguous speakers.
- Uncertain temporal references.
- Negation and polarity errors.

### Phase 4 — Human-in-the-loop evaluation

Use the feedback log to analyse how human review changes the extracted information.

Investigate which errors are easy to correct, which require additional context, and which should trigger explicit abstention.

### Phase 5 — Controlled experimental evaluation

Develop a held-out evaluation set and compare approaches using predefined metrics.

Avoid tuning prompts or system configurations on the final test set.

The longer-term goal is to determine whether evidence-constrained extraction and uncertainty-aware processing can make clinical documentation systems more transparent and dependable.

---

## 9. Project Status

Clinical Scribe currently demonstrates an end-to-end workflow:

**Recorded conversation → Multilingual transcription → Local clinical fact extraction → Evidence-linked draft note → Human review → Feedback logging.**

The current implementation is intended as a foundation for research experiments, not as evidence that automated clinical documentation is already reliable.

The central research interest is not simply whether a language model can produce a plausible clinical note. It is whether the system can explain where each extracted fact came from, preserve what the conversation actually supports, and recognise when it should not make a claim.

---

## Acknowledgements and References

- [ElevenLabs Speech-to-Text Documentation](https://elevenlabs.io/docs/capabilities/speech-to-text)
- [Ollama Documentation](https://ollama.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)

