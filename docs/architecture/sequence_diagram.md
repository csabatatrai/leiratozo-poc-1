# Szekvenciadiagram — batch és élő mód

Szabványos UML szekvenciadiagram, minden szinkron hívásnál `+`/`-`
aktiváció-jelöléssel (a lifeline-okon megjelenő aktivációs sávok pontosan a
hívástól a válaszig tartanak). Ugyanaz a diagram szerepel a fő
[`README.md`](../../README.md) "Működés — szekvenciadiagram" szakaszában is —
ez a fájl az önálló, `docs/architecture/`-beli referencia-változata.

```mermaid
sequenceDiagram
    autonumber
    participant Consumer as Hívó szolgáltatás
    participant API as Worker API (FastAPI)
    participant VAD
    participant Diar as Diarizer
    participant Emb as Embedding
    participant Store as Enrollment Store
    participant ASR as Külső ASR végpont

    rect rgb(232,240,254)
    note over Consumer,ASR: Batch mód — POST /v1/transcribe
    Consumer->>+API: hangfájl (multipart)
    API->>+VAD: csendvágás (ha diarizáció=none)
    VAD-->>-API: csendhatárok
    API->>+Diar: diarize(audio)
    Diar-->>-API: beszélő-szegmensek
    loop szegmensenként (a gyakorlatban párhuzamosan fut)
        API->>+Emb: embed(szegmens)
        Emb-->>-API: embedding-vektor
        API->>+Store: legjobb egyezés (cos-sim)
        Store-->>-API: enrolled_id vagy nincs egyezés
        API->>+ASR: POST /audio/transcriptions
        ASR-->>-API: szöveg + konfidencia
    end
    API-->>-Consumer: Transcript JSON (beszélőnként)
    end

    rect rgb(255,244,224)
    note over Consumer,ASR: Élő mód — WS /v1/transcribe/stream
    Consumer->>+API: WebSocket connect
    API-->>-Consumer: {type: ready}
    loop PCM16 audio-chunkok
        Consumer->>+API: bináris audio chunk
        API->>+VAD: beszéd/csend detektálás
        VAD-->>-API: állapot
        alt elég záró csend, vagy puffer betelt
            API->>+Diar: diarize(puffer)
            Diar-->>-API: szegmensek
            API->>+Emb: embed(szegmensek)
            Emb-->>-API: embeddingek
            API->>+Store: egyezés-keresés
            Store-->>-API: eredmény
            API->>+ASR: transcribe(szegmensek)
            ASR-->>-API: szövegek
            API-->>Consumer: {type: final_segment}
        else beszéd folyamatban
            API->>+ASR: gyors ASR a farok-részre
            ASR-->>-API: részleges szöveg
            API-->>Consumer: {type: partial_segment}
        end
        deactivate API
    end
    Consumer->>+API: kapcsolat bontása
    API-->>-Consumer: {type: closed}
    end
```
