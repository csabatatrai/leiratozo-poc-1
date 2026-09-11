# Manuális teszt-tapasztalatok (2026-09-11 – 2026-09-12)

Ez a dokumentum a `meeting-speaker-adaptation` worker első, kézi/valós-adatos
tesztkörének tapasztalatait, az így talált hibákat és javításokat, valamint a
még **nem** lefedett részeket rögzíti — kiegészítésként a
[`tradeoffs_and_decisions.md`](tradeoffs_and_decisions.md) tervezési döntéseihez.

## 0. Gyors áttekintés — mi van már tesztelve

| # | Terület | Állapot | Mivel/hogyan lett igazolva | Ha ❌ — mi kell a teszteléséhez |
|---|---|---|---|---|
| 1 | ASR-adapter valós, idegen végponttal (`generic` backend) | ✅ | Valós `/transcribe` végpont, saját `GenericAsrClient` kóddal, szintetizált + valós hangon (ld. 1.1, 1.2) | — |
| 2 | Audio-dekódolás (ffmpeg, tetszőleges formátum/mintavételi ráta) | ✅ | 44.1kHz sztereó, 153 MB-os valós WAV helyesen dekódolva 16kHz monóra | — |
| 3 | VAD (csend levágása) | ✅ | `silero` backenddel, valós felvételen (elejéről/végéről helyesen vágott) | — |
| 4 | VAD (`webrtcvad`, az alapértelmezett) | ✅ | Csak izolált Docker-build szinten (natív fordítás gcc-vel) — futásidejű viselkedés nem lett külön ellenőrizve | Egy tényleges pipeline-futtatás `VAD_BACKEND=webrtcvad`-dal (ehhez elég egy gcc-vel rendelkező gép/konténer) |
| 5 | Beszélő-embedding kinyerés (`speechbrain_ecapa`) | ✅ | Valós 15 perces felvételen, hibátlanul lefutott | — |
| 6 | Beszélő-embedding kinyerés (`pyannote_embedding`, az alapértelmezett) | ❌ | — | Érvényes `HF_TOKEN` + a `pyannote/embedding` licenc elfogadása a HuggingFace oldalán |
| 7 | Batch pipeline vég-az-végig (decode → VAD → embedding → enrollment-match → ASR → összefésülés) | ✅ | Teljes 911.8s valós felvétel, 301.4s alatt, hibátlan kimenettel (ld. 1.2) | — |
| 8 | Kimeneti JSON-séma (`Transcript`, `TranscriptSegment` stb.) | ✅ | Unit tesztek + a valós futtatás kimenetének kézi ellenőrzése | — |
| 9 | SRT/VTT export | ✅ | Unit teszt szintetikus transcript-tel | — |
| 10 | Enrollment-tároló (fájl-alapú CRUD, futó-átlagos frissítés) | ✅ | Unit teszt szintetikus vektorokkal, `path traversal` elleni védelem is | — |
| 11 | Enrollment cos-sim egyeztetés logikája | ✅ | Unit teszt (`cosine_similarity`), de csak szintetikus, nem valós hang-embeddinggel | — |
| 12 | **Diarizáció** (`pyannote`, több beszélő szétválasztása) | ❌ | — | Érvényes `HF_TOKEN` a `pyannote/speaker-diarization-3.1`-hez, **és** egy **legalább 2, ismert/megkülönböztethető beszélőt tartalmazó, legalább 3–5 perces** felvétel (rövidebbön a diarizáció minőségét nehéz megítélni; legyen benne mindkét beszélőtől néhány önálló, egymást nem átfedő megszólalás is, ne csak folyamatos átfedés) |
| 13 | **Enrollment végponttól-végpontig** (regisztrált hang felismerése egy másik felvételben) | ❌ | — | Legalább **2 különböző ember tiszta, kb. 2–5 perces hangmintája** (`POST /v1/speakers`-hez) **+** egy **harmadik, ezektől eltérő tesztfelvétel**, amiben mindkét regisztrált hang elhangzik (ideális esetben egy **harmadik, nem regisztrált** beszélő hangjával keverve, hogy az "idegen hang helyesen marad anonim" eset is ellenőrizhető legyen) |
| 14 | Élő (streaming, WS) mód valós hangforrással | ❌ | — | Egy egyszerű kliens-szkript, ami egy hangfájlt valós idejű ütemben, PCM16/16kHz/mono chunkokban küld a `WS /v1/transcribe/stream`-re, és méri a `final_segment` megérkezéséig eltelt időt a beszéd végétől számítva |
| 15 | Teljes `docker build` a végleges `requirements.txt`-tel (torch+pyannote+speechbrain együtt) | ❌ | Csak a `webrtcvad`-részlet lett izoláltan ellenőrizve (ld. 2.2) | Egy gép/CI-futó, aminek elég memóriája van, és semmi más nehéz folyamat nem fut rajta párhuzamosan a build alatt |
| 16 | `docker compose up` — a ténylegesen felépített konténer(ek) indítása és hívása | ❌ | Csak `docker compose config` (syntaktikai) validálás történt | A #15 sikeres build után egy tényleges `docker compose up` + `curl` a felépült konténer ellen |
| 17 | GPU-s futtatás (`DIARIZATION_DEVICE=cuda`/`EMBEDDING_DEVICE=cuda`) | ❌ | — | Egy CUDA-képes gép/konténer `nvidia-container-toolkit`-tel |
| 18 | Több worker-replika + megosztott enrollment-tároló egyidejű írása | ❌ | — | 2 futó worker-példány, ugyanarra a megosztott `ENROLLMENT_STORE_PATH`-ra mutatva, egyidejű `POST /v1/speakers` hívásokkal ugyanarra a névre (ld. [`tradeoffs_and_decisions.md`](tradeoffs_and_decisions.md) 4.6 — ismert race condition, ezt kellene ténylegesen reprodukálni/megmérni) |
| 19 | Terhelés/konkurrencia (több egyidejű `/v1/transcribe` hívás, nem blokkolja-e egymást) | ❌ | — | Egy egyszerű terhelés-teszt (pl. `hey`/`wrk`/`locust`) néhány párhuzamos kéréssel, mérve, hogy a válaszidő nem nő-e lineárisan a konkurrens kérések számával (ez igazolná az `asyncio.to_thread`-es nem-blokkoló dizájnt ténylegesen, nem csak elméletben) |

## 1. Mit teszteltünk

### 1.1 ASR-adapter valódi, külső végponttal

A `curl -F "file=@felvetel.wav" http://192.168.100.7:8001/transcribe` által
elért, tőlünk teljesen független ASR-szerver ellen teszteltük a worker saját
`GenericAsrClient`-jét (nem csak nyers `curl`-lal).

**Megállapítás:** ez a végpont **nem** az OpenAI Whisper API dialektust
beszéli — az útvonala közvetlenül `/transcribe` (nem `<url>/audio/
transcriptions`), a válasza pedig `{"text", "language", "language_probability",
"duration_s", "processing_time_s", "rtf", "segments"}` alakú (részben hasonlít
az OpenAI-sémára, de nem azonos vele). Ez pontosan az az eset, amire a
`generic` ASR-backend készült:

```
ASR_BACKEND=generic
ASR_ENDPOINT_URL=http://192.168.100.7:8001/transcribe
ASR_GENERIC_AUDIO_FIELD=file
ASR_GENERIC_RESPONSE_TEXT_PATH=text
```

A worker saját kódja (`app/core/asr/generic.py`) helyesen dekódolta, elküldte
és feldolgozta a választ egy szintetizált (`espeak-ng`) magyar tesztmondaton —
**eredmény:** a szöveg szó szerint helyesen jött vissza.

### 1.2 Teljes batch pipeline, valós ~15 perces felvételen

Bemenet: `felvetel.wav` — 44.1kHz sztereó PCM, **911.8 másodperc** (kb. 15:12),
153 MB, egy valós magyar hírműsor-interjú részlet (Magyar Önkormányzatok
Szövetsége témában).

Konfiguráció, amivel ténylegesen futott (ld. 2. pont, miért ezekkel):

```
ASR_BACKEND=generic + a fenti végpont
VAD_BACKEND=silero
DIARIZATION_BACKEND=none
EMBEDDING_BACKEND=speechbrain_ecapa
ENROLLMENT_STORE_BACKEND=file (üres tároló)
```

**Eredmény:**
- Végigfutott hiba nélkül, **301.4 másodperc** alatt (RTF ≈ 0.33 — a
  feldolgozás a valós idő harmada alatt végzett, beleértve a VAD-ot, az
  embedding-kinyerést és magát a hálózaton át futó ASR-hívást is).
- A VAD helyesen vágta le a felvétel elejéről/végéről a néma szakaszokat
  (`start=5.7s`, a 911.8s-os teljes hosszból `end=906.5s`-ig tartott a
  detektált beszéd).
- A kimeneti leirat **15 405 karakter**, koherens, a valós elhangzottakkal
  egyező szöveg (tulajdonnevek — pl. "Magyar Péter", "Gémesi György" —
  helyesen felismerve).
- A `Transcript.models` mező helyesen adta vissza a ténylegesen használt
  backendeket/modelleket (ld. 2.1 — ez menet közben derült ki, hogy eredetileg
  NEM volt helyes).

## 2. Talált hibák és javításaik

### 2.1 [JAVÍTVA] `EmbeddingSettings.model` alapértéke nem backend-függő

**Tünet:** amikor `EMBEDDING_BACKEND=speechbrain_ecapa`-t állítottunk be
anélkül, hogy `EMBEDDING_MODEL`-t is felülírtuk volna, a kimeneti
`Transcript.models.embedding_model` mező tévesen `"pyannote/embedding"`-et
mutatott, miközben ténylegesen `speechbrain/spkrec-ecapa-voxceleb` futott.

**Ok:** az `EmbeddingSettings.model` mezőnek egyetlen, fix alapértéke volt
(`"pyannote/embedding"`), függetlenül a kiválasztott backendtől; a
`SpeechBrainEcapaExtractor` pedig egyáltalán nem is használta a `settings.
model` mezőt — hardcode-olva volt a forrás.

**Javítás** (`app/config.py`, `app/core/embedding.py`):
- `SpeechBrainEcapaExtractor` mostantól `self.settings.model`-t használja
  forrásként (konzisztensen a pyannote-extractorral).
- `EmbeddingSettings`-hez került egy `@model_validator(mode="after")`, ami
  `speechbrain_ecapa` backend + a pyannote-alapértékkel egyező `model` mező
  esetén automatikusan a helyes speechbrain-alapértékre vált — explicit
  `EMBEDDING_MODEL` megadása esetén azt tiszteletben tartja.

**Ellenőrzés:** unit teszttel (`EmbeddingSettings(backend="speechbrain_ecapa")
.model == "speechbrain/spkrec-ecapa-voxceleb"`) és a teljes pipeline-futtatás
kimenetében is (ld. 1.2 eredménye) megerősítve.

### 2.2 [JAVÍTVA] `Dockerfile`: hiányzó C-fordító a `webrtcvad` telepítéséhez

**Tünet:** a fejlesztői gépen (ami nem a worker Docker-image-e, hanem egy
sima Python-venv ezen a gépen) a `pip install webrtcvad` natív-kiterjesztés-
fordítási hibával elszállt: `error: [Errno 2] No such file or directory:
'gcc'`.

**Miért releváns ez a Dockerfile-ra nézve is:** a `webrtcvad` az
alapértelmezett `VAD_BACKEND`, és a `requirements.txt` része. A `Dockerfile`
`deps` rétege a build pillanatában **`python:3.11-slim` alapképet** használt,
ami **nem** tartalmaz C-fordítót — vagyis a **`docker build` ugyanígy elhasalt
volna** a `webrtcvad` telepítésén, ha ezt nem vesszük észre.

**Javítás** (`Dockerfile`): a `deps` réteg (csak a build-időhöz szükséges
köztes réteg, nem kerül be a végleges image-be) elején hozzáadtuk:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*
```

**Ellenőrzés:** egy kis, elkülönített, csak `webrtcvad`-ot telepítő
Docker-image-mel (torch/pyannote/speechbrain nélkül, hogy ne legyen újra
memóriaprobléma) megerősítve — `gcc`+`python3-dev` mellett a natív
kiterjesztés hiba nélkül lefordul és importálható.

**Nyitott pont:** a teljes `requirements.txt`-tel (torch+pyannote+speechbrain
együtt) történő valódi `docker build` **még nincs** ebben a környezetben
végigfuttatva — az első ilyen kísérlet a fejlesztői gép memória-erőforrásait
kimerítette (párhuzamosan futott egy másik nehéz Python-folyamattal). Egy
következő, elegendő szabad memóriájú/kizárólagos futtatás során érdemes ezt
is elvégezni.

## 3. Környezeti korlátok, amik NEM a worker hibái

- **Nincs `gcc` a fejlesztői gépen** (csak a Docker image-ben van, a fenti
  javítás után) — ezért a helyi (nem konténerizált) teszteléshez
  `VAD_BACKEND=silero`-t használtunk `webrtcvad` helyett. Ez pusztán a
  tesztkörnyezet korlátja, nem a workeré — Dockerben mindkét backend elérhető.
- **Nincs `HF_TOKEN`** ebben a környezetben a gated pyannote-modellekhez
  (`pyannote/speaker-diarization-3.1`, `pyannote/embedding`) — ezért
  `DIARIZATION_BACKEND=none`-nal és `EMBEDDING_BACKEND=speechbrain_ecapa`-val
  (nem gated) teszteltünk. Éles/teljes teszthez egy érvényes HF-token
  szükséges.
- A helyi Python 3.14-es rendszer-interpreterrel `torch.jit.load` egy
  `FutureWarning`-ot dob (`not supported in Python 3.14+`) — a Docker
  image Python 3.11-et használ, ahol ez nem releváns; a figyelmeztetés
  ártalmatlan volt ebben a tesztben is (a modell helyesen betöltődött és
  futott).

## 4. Amit még NEM teszteltünk

- **Valódi diarizáció** (pyannote, több beszélő szétválasztása) — HF-token
  hiányában `DIARIZATION_BACKEND=none` futott, tehát a `felvetel.wav` teljes
  911.8 másodperce **egyetlen** "beszélőként" (`SPEAKER_00`) lett kezelve,
  jóllehet a felvételen ténylegesen legalább két ember beszél (műsorvezető +
  Gémesi György). Az embedding emiatt egy összemosott, több hangból átlagolt
  vektor volt, nem tiszta, egy-beszélős reprezentáció.
- **Enrollment végponttól-végpontig** (`POST /v1/speakers` regisztráció, majd
  utána egy másik felvételben ugyanannak a hangnak a felismerése) — a
  pipeline-teszt üres enrollment-tárolóval futott, tehát a cos-sim egyeztetés
  soha nem talált egyezést (ez helyes/várt viselkedés üres tárolónál, de nem
  bizonyítja, hogy **találna** egyezést egy valódi, regisztrált profillal).
- **Élő (streaming, WS) mód** valós hangforrással.
- **GPU-s futtatás** (`DIARIZATION_DEVICE=cuda`/`EMBEDDING_DEVICE=cuda`).
- **Teljes `docker build`** a végleges `requirements.txt`-tel (ld. 2.2 nyitott
  pontja).

## 5. Javasolt következő lépés a diarizáció+enrollment lefedésére

Két reális út, HF-token nélkül is elkezdhető:

1. **HF-token beszerzése** — ezzel a `pyannote` backendek éles tesztje egy
   lépésben elvégezhető ugyanezen a `felvetel.wav`-on, és összevethető a
   jelen dokumentum 1.2 pontjában mért, diarizáció nélküli kimenettel.
2. **Kézi "szimulált diarizáció"** HF-token nélkül: a meglévő (1.2 pontban
   elkészült) leirat időbélyegei alapján kivágható a felvételből 1-2 tiszta,
   csak-egy-beszélős szakasz (pl. csak Gémesi György beszél), ezek egyike
   regisztrálható `POST /v1/speakers`-en enrollment-profilként, majd egy
   *másik*, ugyanattól a beszélőtől származó szakaszon lefuttatva a pipeline-t
   (`DIARIZATION_BACKEND=none`, mert a szakasz már eleve egy-beszélős)
   ellenőrizhető, hogy a cos-sim egyezés a `EMBEDDING_SIMILARITY_THRESHOLD`
   (alapértelmezett 0.75) fölé kerül-e. Ez a speechbrain (nem gated) embedding-
   gel is elvégezhető, tehát HF-token nélkül is megkezdhető.
