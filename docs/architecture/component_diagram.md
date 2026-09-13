# Komponens-/interfész-diagram (UML Class Diagram jelöléssel)

Mermaid nem támogat natívan klasszikus UML Component Diagram jelölést
(komponens-dobozok + lollipop-interfészek), ezért a legpontosabb, valóban
szabványos UML-eszköz erre a **Class Diagram**, `<<interface>>` stereotype-
okkal, realizációs nyilakkal (`..|>`, üres háromszög — "ez az osztály
implementálja ezt az interfészt") és függőségi nyilakkal (`..>`, "ez az
osztály használja azt"). Ez pontosan visszaadja a worker pluggable-backend
architektúráját: az orchestrátorok (`BatchPipeline`, `StreamingSession`)
kizárólag az interfészeket (`app/core/interfaces.py`) ismerik, sosem a
konkrét implementációkat — ezt fejezi ki a diagramon, hogy a függőségi nyilak
mind az interfész-dobozokba mutatnak, nem a konkrét osztályokba.

```mermaid
classDiagram
    direction LR

    namespace API_reteg {
        class TranscribeAPI {
            +POST /v1/transcribe
        }
        class StreamAPI {
            +WS /v1/transcribe/stream
        }
        class SpeakersAPI {
            +POST /v1/speakers
            +GET /v1/speakers
            +DELETE /v1/speakers/id
        }
    }

    namespace Orchestracio {
        class BatchPipeline {
            +run_batch_pipeline(audio, settings) Transcript
        }
        class StreamingSession {
            +push_chunk(pcm16) StreamEvent[]
            +flush() StreamEvent[]
        }
    }

    namespace Pluggable_interfeszek {
        class VoiceActivityDetector {
            <<interface>>
            +detect(audio, sr) SpeechSegment[]
        }
        class Diarizer {
            <<interface>>
            +diarize(audio, sr, min_spk, max_spk) DiarizedSegment[]
        }
        class EmbeddingExtractor {
            <<interface>>
            +embed(audio, sr) ndarray
            +dimension() int
        }
        class AsrClient {
            <<interface>>
            +transcribe(audio, sr, lang) AsrResult
            +aclose()
        }
        class SpeakerProfileStore {
            <<interface>>
            +upsert(id, name, embedding)
            +get(id) SpeakerProfile
            +all_embeddings() tuple[]
        }
    }

    namespace Konkret_backendek {
        class WebrtcVadAdapter
        class SileroVadAdapter
        class NoOpVad
        class PyannoteDiarizer
        class NoOpDiarizer
        class PyannoteEmbeddingExtractor
        class SpeechBrainEcapaExtractor
        class OpenAICompatibleAsrClient
        class GenericAsrClient
        class FileSpeakerProfileStore
    }

    WebrtcVadAdapter ..|> VoiceActivityDetector
    SileroVadAdapter ..|> VoiceActivityDetector
    NoOpVad ..|> VoiceActivityDetector
    PyannoteDiarizer ..|> Diarizer
    NoOpDiarizer ..|> Diarizer
    PyannoteEmbeddingExtractor ..|> EmbeddingExtractor
    SpeechBrainEcapaExtractor ..|> EmbeddingExtractor
    OpenAICompatibleAsrClient ..|> AsrClient
    GenericAsrClient ..|> AsrClient
    FileSpeakerProfileStore ..|> SpeakerProfileStore

    BatchPipeline ..> VoiceActivityDetector : uses
    BatchPipeline ..> Diarizer : uses
    BatchPipeline ..> EmbeddingExtractor : uses
    BatchPipeline ..> AsrClient : uses
    BatchPipeline ..> SpeakerProfileStore : uses

    StreamingSession ..> VoiceActivityDetector : uses
    StreamingSession ..> Diarizer : uses
    StreamingSession ..> EmbeddingExtractor : uses
    StreamingSession ..> AsrClient : uses
    StreamingSession ..> SpeakerProfileStore : uses

    TranscribeAPI ..> BatchPipeline : hivja
    StreamAPI ..> StreamingSession : letrehozza
    SpeakersAPI ..> SpeakerProfileStore : hasznalja
    SpeakersAPI ..> EmbeddingExtractor : hasznalja

    class AsrEndpoint {
        <<external>>
        ASR_ENDPOINT_URL
    }
    OpenAICompatibleAsrClient ..> AsrEndpoint : HTTP
    GenericAsrClient ..> AsrEndpoint : HTTP
```

**Hogyan olvasd:** minden `Konkret_backendek` névtérbeli osztály pontosan egy
interfészt valósít meg (`..|>`), és a `config.py`-ban megadott
`*_BACKEND` env-változó dönti el futásidőben, melyik konkrét osztály épül be
— az orchestrátorok kódja ettől függetlenül, változatlanul ugyanazt az
interfészt hívja. Egy új modell/könyvtár bevezetése tehát mindig egy új,
az adott interfészt megvalósító osztály hozzáadását jelenti, az
`Orchestracio` és `API_reteg` névterek egyetlen sorát sem érintve.
