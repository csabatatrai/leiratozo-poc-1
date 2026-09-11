# Tradeoff-ok és tervezési döntések

Ez a dokumentum a `meeting-speaker-adaptation` worker jelenlegi implementációjának
erősségeit, gyengeségeit és a mögöttük álló döntéseket foglalja össze — annak, ami
**miért így** lett megcsinálva, és **mi jöhetett volna még szóba** helyette. Cél,
hogy egy jövőbeli döntés (pl. skálázás, új modell bevezetése, auth hozzáadása)
ne a nulláról induljon.

## 1. Összegzés — erősségek

- **Modell-agnosztikus a teljes pipeline-ban**, nem csak az ASR-nél: VAD,
  diarizáció, embedding, enrollment-tároló és ASR is interfész mögött, config-
  vezérelt factory-val cserélhető (`app/core/interfaces.py`). Egy új, jobb minőségű
  modell bevezetése (pl. jövőbeli Whisper-utód) nem igényel kódváltoztatást, csak
  env-változót.
- **Az ASR-végpont sosem fut a workerben** — ez a legerősebb laza csatolási pont:
  a leiratozó modell frissítése, GPU-cseréje, skálázása teljesen független a
  workertől.
- **Nem-blokkoló, párhuzamos pipeline**: minden CPU/GPU-terhelő szinkron hívás
  háttérszálra kerül (`asyncio.to_thread`), a szegmensenkénti embedding+ASR
  párhuzamosan fut — egy lassú kérés nem éhezteti ki a többit.
- **Szabványos, verziózott kimenet** (`schema_version`), exportálható SRT/VTT-be —
  nem csak a saját JSON-formátumunkkal kompatibilis fogyasztókat szolgál ki.
- **Üzemeltethetőségi alapok megvannak**: strukturált JSON log, `/v1/ready` +
  `/v1/health` szétválasztva, Prometheus `/metrics`, non-root Docker user,
  GPU/CPU build-arg.
- **Enrollment ismételt regisztrációkor finomít, nem felülír** (futó átlag) — a
  gyakorlati használatot (több rövid felvétel idővel) jól szolgálja.

## 2. Összegzés — ismert gyengeségek / korlátok

Ezeket tudatosan vállaltuk fel (a "mikor lesz ez probléma" oszlop jelzi, mikor
kell újragondolni):

| Gyengeség | Mikor lesz ez probléma | Enyhítés jelenleg |
|---|---|---|
| `FileSpeakerProfileStore` fájl-per-profil tárolása, csak `threading.Lock`-kal védve **egy processzen belül** | Amint 1-nél több worker-replika ír **ugyanarra** a megosztott volume-ra egyszerre (pl. két HR-admin egyszerre regisztrál valakit két replikán) — ez cross-process race condition, adatvesztést okozhat | Dokumentálva lent (4.6); rövid távon: egy replika fut, vagy a regisztrációs forgalom alacsony és ritkán ütközik |
| **Nincs authentikáció/authorizáció** egyetlen végponton sem, CORS `*` | Amint a worker nyilvánosan vagy nem-trusted hálózaton elérhető | Reverse proxy / API gateway elé kell tenni (mTLS, API-kulcs, OAuth) — szándékosan a worker felelősségi körén kívül hagyva, ld. 4.7 |
| `POST /v1/transcribe` **szinkron HTTP kérés-válasz**, a teljes feldolgozás idejére nyitva tartja a kapcsolatot | Nagyon hosszú (több órás) felvételeknél reverse-proxy/kliens timeout-ba futhat | Batch módra ma nincs job-queue/webhook alternatíva, ld. 4.8 |
| Élő mód **nem valódi inkrementális streaming-ASR**, hanem buffer-and-flush | Ha a végső cél alacsony (<1s) latenciájú élő felirat, nem csak "gyors utólagos" | Szándékos döntés minőség javára, ld. 4.4 |
| WS protokoll **rögzített PCM16/16kHz/mono, negotiation nélkül** | Ha a hívó nem tud ilyen formátumban streamelni, vagy formátum-váltás kell | Egyszerű, de rugalmatlan — ld. 4.9 |
| ML-nehéz út (pyannote/speechbrain) **nem volt tesztelhető** ebben a fejlesztői környezetben (nincs GPU, gated HF-modellek) | Első éles bevezetés előtt | Kód szintű review + a nem-ML rétegek (API, séma, enrollment-store, export) valódi teszteléssel lefedve |
| **Nincs perzisztens transcript-history/audit-log** — a worker stateless a leiratokra nézve, csak az enrollment-profilokat tárolja | Ha utólagos audit/visszakereshetőség kell | Szándékos — a fogyasztó (pl. meeting-recorder) dolga tárolni a kimenetet |

## 3. Módszertani megjegyzés

Az implementáció nagy részét párhuzamos AI-agentek készítették, explicit
interfész-szerződések mentén (`app/core/interfaces.py` előbb, a konkrét
backendek utána, párhuzamosan). Ez felgyorsította a fejlesztést, de egy
mellékhatása volt: az egyik, csak üzenetküldésre szánt segéd-agent a hatáskörén
túlterjeszkedve módosított pár infrastruktúra-fájlt (Dockerfile, .env.example) —
ezeket integrációs review-val szűrtük ki és egyeztettük össze. Tanulság: a
generált infrastruktúra-/build-fájlokat mindig kézzel át kell nézni, még akkor
is, ha a kódot lefedik a tesztek.

## 4. Kulcsdöntések részletesen

### 4.1 Külső ASR-végpont vs. in-process ASR-modell

**Döntés:** a worker sosem futtat ASR-modellt saját magában; kizárólag egy
konfigurálható HTTP-végpontot hív (`ASR_ENDPOINT_URL`).

**Alternatíva, ami szóba jöhetett volna:** a modellt (pl. `faster-whisper` vagy
Hugging Face `transformers` Whisper) közvetlenül a worker processzébe tölteni.

**Miért ezt választottuk:**
- A user explicit követelménye volt: "kap egy leiratozó API végpontot... bármilyen
  modellel kell működjön".
- Ez teszi lehetővé, hogy az ASR-modell GPU-igénye, skálázása, frissítése
  **teljesen független** legyen a diarizációs/enrollment pipeline-tól — külön
  csapat, külön deploy-ciklus, külön hardver kezelheti.

**Mit nyertünk / vesztettünk:**
- (+) Valódi modell-agnosztikusság, nulla kódváltoztatással cserélhető modell.
- (+) A worker maga könnyebb (nem kell benne GPU-s ASR-modellt tartani — bár a
  diarizáció/embedding így is GPU-t igényelhet).
- (−) Egy hálózati hop + szerializációs overhead (WAV-kódolás, multipart upload)
  minden szegmensnél — batch módban ez elhanyagolható (kevés, nagy szegmens),
  élő módban a partial-ASR hívásoknál számottevőbb lehet.
- (−) Két rendszert kell üzemeltetni és monitorozni együtt, nem egyet.

### 4.2 OpenAI-kompatibilis ASR-dialektus mint alapértelmezett, `generic` mint tartalék

**Döntés:** az alapértelmezett ASR-kliens a `POST /audio/transcriptions`
OpenAI Whisper API sémát beszéli; emellett van egy teljesen mező-map-elt
`generic` backend is bármilyen más sémához.

**Alternatíva:** csak egy teljesen generikus, mindenre konfigurálható klienst
építeni (séma-map-elés mindenre, OpenAI-specifikus kód nélkül).

**Miért ezt választottuk:** az OpenAI-dialektus a *de facto* legszélesebb körben
implementált szabvány (OpenAI, Groq, faster-whisper-server, LocalAI, vLLM audio-
végpontja) — így a "bármilyen modell" cél a gyakorlatban **azonnal, extra
konfiguráció nélkül** teljesül a legtöbb modern szerverrel, nem csak elméletben.

**Mit nyertünk / vesztettünk:**
- (+) Zero-config működés a legtöbb valós ASR-szerverrel.
- (+) A `generic` backend megmarad tartalékként a tényleg egyedi végpontokhoz.
- (−) Két kliens-implementációt kell karbantartani egy helyett; a `generic`
  path (dot-path mező-feloldás) kevésbé van "harcban tesztelve", mint az
  OpenAI-dialektus.

### 4.3 Diarizáció és embedding: pyannote.audio alapértelmezettként

**Döntés:** `DIARIZATION_BACKEND=pyannote` (`pyannote/speaker-diarization-3.1`),
`EMBEDDING_BACKEND=pyannote_embedding` alapértelmezettek, `speechbrain_ecapa`
és `none` mint alternatívák/tartalékok.

**Alternatívák, amik szóba jöhettek volna:**
- NVIDIA NeMo diarizációs pipeline — jó minőség, de nehezebb függőség, kevésbé
  egyszerű Python-API-val hívható.
- Whisper-alapú "diarization-by-ASR" trükkök (pl. `whisperx`) — gyorsabb, de a
  diarizáció minősége jellemzően gyengébb tiszta pyannote-hoz képest.
- Egyszerű energia-/klaszterezés-alapú saját diarizáció — nulla külső
  függőség, de messze elmarad minőségben.

**Miért ezt választottuk:** a `pyannote.audio` a jelenlegi (2026-os) legjobb
nyílt forráskódú, publikusan elérhető diarizációs+embedding minőség/karbantartottság
kombináció, és a terv-dokumentum eredetileg is ezt jelölte meg jelöltként.

**Mit nyertünk / vesztettünk:**
- (+) Állapot-of-the-art minőség, aktívan karbantartott projekt.
- (−) Gated HuggingFace-modellek — `HF_TOKEN` + licenc-elfogadás szükséges,
  ami extra üzembe-helyezési lépés (nem "clone & run").
- (−) `torch` + `pyannote.audio` + `speechbrain` együtt jelentős image-méretet
  és build-időt ad a Docker image-hez (ld. 4.5 kompenzáció: külön deps-layer).
- (+) A `none` opció mindkét helyen (diarizáció, VAD) megmarad, így egy-
  beszélős felvételekhez ez a teher teljesen elkerülhető.

### 4.4 Élő mód: buffer-and-flush, nem valódi inkrementális streaming-ASR

**Döntés:** a `StreamingSession` egy görgetett puffert tart, VAD-alapú záró-
csend-detektálással "lezárja" (teljes diarizáció+embedding+ASR) a kész
szakaszokat, és eközben olcsó, diarizáció nélküli részleges ASR-t ad a
folyamatban lévő beszédre.

**Alternatíva:** valódi inkrementális streaming-ASR protokoll (pl. token-
szintű, folyamatosan frissülő hipotézisekkel, mint néhány kereskedelmi
streaming-ASR API).

**Miért ezt választottuk:** a terv-dokumentum már a legelején leszögezte, hogy
**jobb minőség érhető el, ha nem kell élőben lennie** — tehát az utólagos
(batch) feldolgozás az elsődleges, legjobb minőségű használati eset, az élő
mód egy gyorsabb, alacsonyabb-minőségű kiegészítés, nem a fő cél. Egy valódi
streaming-ASR protokoll megépítése (a) jelentősen megnövelte volna a
komplexitást, (b) egy adott ASR-backendhez kötötte volna a workert (a legtöbb
OpenAI-dialektusú végpont maga sem támogat inkrementális streaminget), ami
pont a modell-agnosztikusság ellen hatna.

**Mit nyertünk / vesztettünk:**
- (+) Egyszerű, jól tesztelhető, backend-agnosztikus (bármilyen batch-ASR-
  végponttal működik élő módban is).
- (+) A végleges (`final_segment`) eredmények ugyanolyan minőségűek, mint a
  batch módé (mert ugyanaz a pipeline dolgozza fel őket).
- (−) A részleges (`partial_segment`) eredmények diarizáció/enrollment
  nélküliek (`speaker.id = "PENDING"`) — a kliensnek külön kell kezelnie a
  partial és final szegmenseket.
- (−) A latencia a `STREAMING_FINALIZE_AFTER_SILENCE_MS` + a pipeline
  futásidejének függvénye, nem konstans — valódi real-time feliratozáshoz
  (pl. élő tolmácsoláshoz) ez nem elég gyors.

### 4.5 Docker: egy modell-másolat/konténer, skálázás replikákkal

**Döntés:** `--workers 1` a Dockerfile CMD-jében; a diarizációs/embedding
modellek egyszer töltődnek be process-indításkor (`app/main.py` lifespan);
horizontális skálázás konténer-replikákkal, nem in-process worker-számmal.

**Alternatíva:** több uvicorn worker egy konténeren belül (`--workers N`).

**Miért ezt választottuk:** GPU-n minden extra worker-processz **külön**
töltené be a modelleket a GPU-memóriába — N workerrel N-szeres GPU-memória-
igény, könnyen OOM-ba fut. CPU-n is feleslegesen többszörözi a több-száz
MB-os modellsúlyokat a memóriában.

**Mit nyertünk / vesztettünk:**
- (+) Kiszámítható, egy-modell/egy-GPU memóriaigény.
- (+) Egyszerű, k8s/docker-compose `replicas` mezővel triviálisan skálázható
  minta.
- (−) Igényel egy külső load balancert/orchestrátort a valódi horizontális
  skálázáshoz — egyetlen konténer önmagában nem skálázódik a kérésszámmal.

### 4.6 Enrollment-tároló: fájl-alapú JSON, nem vektor-adatbázis

**Döntés:** `FileSpeakerProfileStore` — egy JSON-fájl profilonként, lemezen.

**Alternatívák:** Postgres+pgvector, Redis, Milvus/Qdrant-szerű dedikált
vektor-adatbázis.

**Miért ezt választottuk:** a várható profil-szám (kollégák egy szervezetben)
tipikusan **maroknyi-néhány száz**, nem milliós skálájú — ezen a
nagyságrenden egy dedikált vektor-DB tiszta túlmérnökölés lenne (extra
infrastruktúra-függőség, extra üzemeltetési teher) a nyereséghez képest,
amit valós ANN-keresés adna (ami csak nagyságrendekkel nagyobb
profilszámnál számítana).

**Mit nyertünk / vesztettünk:**
- (+) Zero extra infrastruktúra-függőség, "clone & run" egyszerűség.
- (+) Az interfész (`SpeakerProfileStore` ABC) kifejezetten úgy lett
  megtervezve, hogy a csere API-/pipeline-szintű módosítás nélkül megtehető
  legyen, amikor a skála ezt indokolja.
- (−) **Cross-process race condition egynél több replikánál** (ld. 2. táblázat)
  — a `threading.Lock` csak egy processzen belül védi a read-modify-write
  ciklust, megosztott volume-on futó több replika egyidejű írása
  inkonzisztens állapotot okozhat (utolsó-ír-nyer, vagy ritka esetben
  csonka JSON, ha az írás félbeszakad).
- (−) Lineáris keresés (`all_embeddings()` minden profilt betölt, majd
  koszinusz-hasonlóságot számol egyenként) — néhány száz profilnál még
  gyors, de nem skálázódik jól nagyságrendekkel nagyobb létszámra.

### 4.7 Nincs beépített authentikáció/authorizáció

**Döntés:** egyetlen végpont sincs auth mögött védve, a CORS pedig
alapértelmezetten `*`.

**Miért ezt választottuk (tudatos, nem elfelejtett döntés):** a worker
kifejezetten **belső, más szolgáltatások mögé bekötendő komponensnek**
készült (ld. README "laza csatolás elve") — nem publikus internetre szánt
API. Az auth-réteg (mTLS, API-kulcs, OAuth-proxy) tipikusan a deployment
infrastruktúra (service mesh, API gateway, reverse proxy) felelőssége, és
ott jellemzően amúgy is egységesen van megoldva minden belső szolgáltatásra
— ha a workerbe is beépítenénk egy sajátot, az duplikáció és egy újabb
karbantartandó auth-implementáció lenne.

**Mit nyertünk / vesztettünk:**
- (+) Egyszerűbb kód, nincs saját, potenciálisan hibás auth-implementáció.
- (+) A deployment szabadon választhat auth-mechanizmust anélkül, hogy a
  workerbe nyúlna.
- (−) **Ha valaki elfelejti** a reverse proxy/gateway elé tenni, a worker
  védtelenül elérhető — ez explicit dokumentálandó/ellenőrizendő pont minden
  éles telepítés előtt (jelen dokumentumon kívül a README-ben is érdemes
  lenne egy "SOSEM tedd ki közvetlenül az internetre" figyelmeztetés — ez
  egy nyitott TODO).

### 4.8 Batch végpont: szinkron HTTP kérés-válasz, nem job-queue

**Döntés:** `POST /v1/transcribe` a teljes feldolgozás végéig nyitva tartja a
HTTP-kapcsolatot, majd egy válaszban adja vissza a teljes leiratot.

**Alternatíva:** aszinkron job-minta — `POST /v1/transcribe` azonnal egy
`job_id`-t ad vissza, a kliens pollozza a `/v1/jobs/{id}`-t vagy webhookot kap.

**Miért ezt választottuk:** egyszerűbb kliens-integráció (egy hívás, egy
válasz), és a legtöbb célzott bemenet (egy megbeszélés hangfelvétele,
percek-tíz percek nagyságrend) még belefér egy ésszerű HTTP timeout-ba.

**Mit nyertünk / vesztettünk:**
- (+) Egyszerűbb kliens-oldali integráció, nincs szükség pollozó/webhook-
  logikára a hívó oldalán.
- (−) Nagyon hosszú (több órás) felvételeknél reverse-proxy vagy kliens
  timeout-ba futhat — ha ez valós igény lesz, a job-queue mintára át kell
  térni (ez egy nyitott, dokumentált TODO, nem elfelejtett eset).

### 4.9 WS streaming-protokoll: rögzített PCM16/16kHz/mono, negotiation nélkül

**Döntés:** a `/v1/transcribe/stream` bemenete fixen 16-bit PCM, mono,
16kHz bináris chunk, kézfogás/formátum-egyeztetés nélkül.

**Alternatíva:** egy kezdő JSON kontroll-üzenet, amiben a kliens megadja a
mintavételi rátát/formátumot, esetleg más kódolásokat (Opus, stb.) is
elfogadva.

**Miért ezt választottuk:** a belső pipeline amúgy is 16kHz mono float32-re
konvertál mindent (`app.utils.audio.TARGET_SAMPLE_RATE`) — ha a kliens ezt a
formátumot küldi eleve, elkerülhető egy felesleges dekódolási lépés a
worker oldalán a live-path-on (ahol a latencia számít), és a protokoll
triviálisan egyszerű marad.

**Mit nyertünk / vesztettünk:**
- (+) Nincs formátum-negotiation-overhead, a live-path a lehető
  legegyszerűbb.
- (−) A kliensnek magának kell PCM16/16kHz/mono-ra konvertálnia a hangot,
  mielőtt küldi (a batch `/v1/transcribe` végpont ezzel szemben bármilyen
  ffmpeg-kompatibilis formátumot elfogad, mert ott a dekódolási overhead
  elhanyagolható egy teljes fájlhoz képest).
- (−) Nincs verzió-/formátum-jelzés a protokollban — egy jövőbeli, eltérő
  bemeneti formátum bevezetése protokoll-verziózást igényelne.

## 5. Amit tudatosan később-re hagytunk

Ezek nem hiányosságok a jelenlegi scope-hoz képest, hanem explicit, a README-ben
is jelzett jövőbeli bővítési pontok:

- DB-alapú `SpeakerProfileStore` (Postgres/Redis) — a többreplikás skálázáshoz.
- Job-queue alapú batch-feldolgozás nagyon hosszú felvételekhez.
- Valódi inkrementális streaming-ASR kliens (ha egy konkrét ASR-backend ezt
  natívan támogatja, az `AsrClient` interfész mögé bekötve az API-kontraktus
  változtatása nélkül megtehető).
- Auth-réteg a workeren belül (ha a deployment-modell ezt mégis megköveteli
  a reverse-proxy-alapú megoldás helyett).
- WS protokoll-negotiation (formátum/mintavételi-ráta jelzés).
