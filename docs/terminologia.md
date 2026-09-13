# Terminológia — IT szakkifejezések szójegyzéke

Ez a szójegyzék azoknak a kifejezéseknek a magyarázatát adja, amelyek a
`meeting-speaker-adaptation` projekt megértéséhez szükségesek. Cél: hogy egy
diák vagy a projektet először látó fejlesztő a `README.md`-t és a kódot úgy
tudja olvasni, hogy minden szakszót ide vissza tud lapozni.

Minden szócikk három részből áll:

- **Általános jelentés** — mit jelent a kifejezés az IT-ben, projekttől
  függetlenül.
- **Hol jelenik meg a projektben** — konkrét fájl/config-kulcs/kódrészlet.
- **Mit old meg a projektben** — miért volt szükség rá, mi lenne nélküle a
  probléma.

A fogalmak témakörönként csoportosítva szerepelnek, nem ábécérendben, mert így
együtt tanulhatók az egymásra épülő dolgok (pl. előbb "hang", utána "VAD",
utána "diarizáció", mert ezek erre a sorrendre épülnek a pipeline-ban).
Egy adott kifejezés gyors megkereséséhez lásd a dokumentum végén az
**ábécérendes gyorskeresőt** (17. szakasz).

## Tartalomjegyzék

1. [Hangfeldolgozás alapfogalmai](#1-hangfeldolgozás-alapfogalmai)
2. [Hangesemény-detektálás (VAD)](#2-hangesemény-detektálás-vad)
3. [Beszélő-szétválasztás (diarizáció)](#3-beszélő-szétválasztás-diarizáció)
4. [Beszélő-felismerés és -regisztráció (enrollment)](#4-beszélő-felismerés-és--regisztráció-enrollment)
5. [Beszédfelismerés (ASR)](#5-beszédfelismerés-asr)
6. [API-tervezés és webes protokollok](#6-api-tervezés-és-webes-protokollok)
7. [Backend-architektúra és tervezési minták](#7-backend-architektúra-és-tervezési-minták)
8. [Aszinkron programozás (Python `asyncio`)](#8-aszinkron-programozás-python-asyncio)
9. [Webkeretrendszer és adatvalidáció (FastAPI, Pydantic)](#9-webkeretrendszer-és-adatvalidáció-fastapi-pydantic)
10. [Megfigyelhetőség (observability)](#10-megfigyelhetőség-observability)
11. [Konténerizáció és üzemeltetés (Docker)](#11-konténerizáció-és-üzemeltetés-docker)
12. [Gépi tanulás / GPU-üzemeltetés](#12-gépi-tanulás--gpu-üzemeltetés)
13. [Tesztelés és minőségbiztosítás](#13-tesztelés-és-minőségbiztosítás)
14. [Egyéb, gyakran előforduló fogalmak](#14-egyéb-gyakran-előforduló-fogalmak)
15. [Hogyan függenek össze ezek? — a pipeline egy mondatban](#hogyan-függenek-össze-ezek--a-pipeline-egy-mondatban)
16. [Hasznos tanulási sorrend kezdőknek](#16-hasznos-tanulási-sorrend-kezdőknek)
17. [Ábécérendes gyorskereső](#17-ábécérendes-gyorskereső)

---

## 1. Hangfeldolgozás alapfogalmai

### PCM (Pulse-Code Modulation)
- **Általános jelentés:** A hang legnyersebb, tömörítetlen digitális
  ábrázolása — a hangnyomást másodpercenként sokszor (a mintavételi
  frekvencia szerint) lemért számsorozatként tárolja.
- **Hol jelenik meg a projektben:** A `WS /v1/transcribe/stream` végpont
  bemenete explicit **"bináris PCM16 mono 16kHz chunk"** (`app/api/stream.py`,
  `app/core/asr/wav_encode.py`). A batch pipeline is PCM-re dekódolja a
  bejövő fájlt (`app/utils/audio.py`).
- **Mit old meg a projektben:** Minden belső komponens (VAD, diarizáció,
  embedding, ASR-kliens) egyetlen, egyszerű, formátum-mentes hangreprezentációt
  vár — nem kell mindegyiknek tudnia MP3-at, OGG-t stb. dekódolni.

### Mintavételi frekvencia (sample rate, pl. 16 kHz)
- **Általános jelentés:** Hányszor mérik meg másodpercenként a hang
  amplitúdóját. Minél magasabb, annál pontosabb a digitalizálás, de annál
  nagyobb az adatmennyiség.
- **Hol jelenik meg a projektben:** A pipeline mindent **16 kHz, mono**
  formátumra egységesít dekódolás után (README architektúra-diagram: "ffmpeg
  dekódolás mono, 16kHz float32").
- **Mit old meg a projektben:** A VAD/diarizációs/embedding modellek fix
  mintavételi frekvenciára vannak tanítva — egységesítés nélkül eltérő
  bemeneti formátumú fájloknál rossz eredményt adnának.

### Mono / csatorna (channel)
- **Általános jelentés:** Egy hangfájl egy vagy több hangcsatornát
  (mono/stereo) tartalmazhat; mono = egyetlen keverék hangsáv.
- **Hol jelenik meg a projektben:** A README explicit kimondja a probléma
  lényegét: "**egy mikrofon, több egyidejű beszélő, egy kevert
  hangcsatorna**" — nem csatornánként külön szétválasztott felvétel.
- **Mit old meg a projektben:** Ez indokolja, hogy miért kell a
  beszélő-szétválasztást magából a hangból kinyerni (diarizáció), nem pedig
  egyszerűen csatornánként azonosítani a beszélőket.

### Kódolás / dekódolás (codec, ffmpeg)
- **Általános jelentés:** A hangfájlok tömörített formátumban
  (MP3, AAC, Opus…) érkeznek; ezeket vissza kell "bontani" nyers PCM
  mintákra a feldolgozáshoz. Az `ffmpeg` egy általánosan használt,
  parancssoros eszköz, amely gyakorlatilag minden hang/videó formátumot
  tud kezelni.
- **Hol jelenik meg a projektben:** `Dockerfile` telepíti az `ffmpeg`
  csomagot ("universal audio decode... used by app/utils/audio.py").
- **Mit old meg a projektben:** Így a `/v1/transcribe` végpont
  bármilyen bejövő hangfájl-formátumot elfogad, nem csak egyet — a
  formátum-függetlenséget ffmpeg biztosítja, nem a saját kódunk.

---

## 2. Hangesemény-detektálás (VAD)

### VAD (Voice Activity Detection, hangaktivitás-detektálás)
- **Általános jelentés:** Algoritmus, amely eldönti egy hangfájl/hangfolyam
  egy adott pillanatáról, hogy beszéd hallható-e rajta, vagy csend/zaj.
- **Hol jelenik meg a projektben:** `app/core/vad.py`,
  `VoiceActivityDetector` interfész (`app/core/interfaces.py`),
  `VAD_BACKEND` config (`webrtcvad` / `silero` / `none`).
- **Mit old meg a projektben:** Kiszűri a csendes/üres szakaszokat, mielőtt
  a drágább (CPU/GPU-igényes) diarizáció vagy ASR-hívás lefutna rajtuk —
  ez gyorsítja a feldolgozást és javítja a pontosságot. Élő módban ez dönti
  el, mikor "záródik le" egy mondat (záró csend detektálása).

### WebRTC VAD (`webrtcvad`)
- **Általános jelentés:** A Google WebRTC projektjéből kiszakított,
  könnyűsúlyú, klasszikus (nem neurális hálós) VAD-implementáció.
- **Hol jelenik meg a projektben:** `VAD_BACKEND=webrtcvad` (alapértelmezett),
  `VAD_AGGRESSIVENESS` (0=laza, 3=szigorú) config-kulcs.
- **Mit old meg a projektben:** Ez az alapértelmezett, mert gyors és nincs
  neurális háló letöltési/GPU-igénye — jó alapérték kis erőforrású
  környezethez.

### Silero VAD
- **Általános jelentés:** Egy kis méretű, neurális hálón (mély tanuláson)
  alapuló VAD-modell, pontosabb, mint a klasszikus módszerek, de nagyobb a
  függősége.
- **Hol jelenik meg a projektben:** `VAD_BACKEND=silero`,
  `silero-vad==5.1.2` a `requirements.txt`-ben.
- **Mit old meg a projektben:** Cserélhető alternatíva, ha a pontosság
  fontosabb, mint az egyszerűség — a config-vezérelt csere elve miatt egy
  env-változó módosításával válthatunk rá kód nélkül.

---

## 3. Beszélő-szétválasztás (diarizáció)

### Diarizáció (speaker diarization)
- **Általános jelentés:** Az a feladat, hogy egy hangfelvételben ("ki mikor
  beszélt?") időszegmensekre bontsuk a hangot, és minden szegmenshez egy
  (a felvételen belül) anonim beszélő-azonosítót rendeljünk — anélkül, hogy
  tudnánk, *ki* az illető valójában.
- **Hol jelenik meg a projektben:** `app/core/diarization.py`, `Diarizer`
  interfész, `DIARIZATION_BACKEND=pyannote` (vagy `none`),
  `DiarizedSegment` dataclass (`speaker_id`, pl. `"SPEAKER_00"`).
- **Mit old meg a projektben:** Ez a projekt lényege — egyetlen kevert
  hangcsatornából kell kibontani, hogy hány beszélő van, és melyik
  hangszakasz melyikhez tartozik, mielőtt bárkit név szerint azonosítanánk.

### pyannote.audio
- **Általános jelentés:** Egy nyílt forráskódú, Python-alapú
  gépi tanulási könyvtár beszélő-diarizációra és -embeddingre, előre
  tanított ("pretrained") modellekkel.
- **Hol jelenik meg a projektben:** `pyannote.audio==3.3.2` a
  `requirements.txt`-ben, `DIARIZATION_MODEL=pyannote/speaker-diarization-3.1`
  alapértelmezett modell.
- **Mit old meg a projektben:** Ez biztosítja a diarizáció konkrét,
  jó minőségű gépi tanulási implementációját — a projekt saját kódja csak
  az interfész mögé köti be, nem maga implementálja az algoritmust.

### Anonim beszélő-azonosító (pl. `SPEAKER_00`)
- **Általános jelentés:** Egy diarizációs futás belső, csak az adott
  hangfelvételre érvényes címkéje — nem valós név, csak "aki elsőnek beszélt
  = SPEAKER_00" jellegű sorszám.
- **Hol jelenik meg a projektben:** `DiarizedSegment.speaker_id`,
  `SpeakerLabel.id` a kimeneti JSON-sémában (`app/schemas.py`).
- **Mit old meg a projektben:** Ez a "nyers" kimenete a diarizációnak,
  mielőtt az enrollment-egyeztetés (4. szakasz) esetleg valós névvel
  helyettesítené.

---

## 4. Beszélő-felismerés és -regisztráció (enrollment)

### Speaker embedding (beszélő-lenyomat / hangvektor)
- **Általános jelentés:** Egy neurális háló egy hangrészletet egy fix
  hosszúságú számvektorrá ("embedding"-gé) alakít úgy, hogy ugyanazon
  beszélő különböző felvételeinek vektorai egymáshoz *közel* essenek egy
  matematikai térben, míg különböző beszélőké távol.
- **Hol jelenik meg a projektben:** `app/core/embedding.py`,
  `EmbeddingExtractor` interfész, `EMBEDDING_BACKEND` (`pyannote_embedding` /
  `speechbrain_ecapa`).
- **Mit old meg a projektben:** Ez teszi lehetővé, hogy két hangrészletet
  ("ki beszélt itt?" vs. "ez a regisztrált Kovács János hangja?")
  matematikailag összehasonlítsunk, nem csak "hallás alapján".

### ECAPA-TDNN (speechbrain_ecapa)
- **Általános jelentés:** Egy konkrét, széles körben használt neurális
  háló-architektúra beszélő-embedding készítésére.
- **Hol jelenik meg a projektben:** `EMBEDDING_BACKEND=speechbrain_ecapa`,
  `speechbrain==1.0.2` csomag, alapértelmezett modell:
  `speechbrain/spkrec-ecapa-voxceleb`.
- **Mit old meg a projektben:** Alternatíva a pyannote-embedding mellett —
  ugyanazt a feladatot más modellel oldja meg, cserélhetően.

### Koszinusz-hasonlóság (cosine similarity)
- **Általános jelentés:** Két vektor "hasonlóságát" mérő matematikai
  művelet, amely a vektorok közti szög koszinuszát adja vissza — értéke
  jellemzően -1 és 1 között van, 1 = teljesen egyező irány.
- **Hol jelenik meg a projektben:** `EMBEDDING_SIMILARITY_THRESHOLD`
  (alapértelmezett `0.75`), `app/core/enrollment/matcher.py`,
  `SpeakerLabel.confidence` mező.
- **Mit old meg a projektben:** Ez a döntési szabály: ha egy diarizált
  beszélő hangvektora elég közel van (≥ küszöb) egy regisztrált profil
  vektorához, a rendszer **név szerint** azonosítja; ha nem, anonim marad
  (`SPEAKER_NN`). Ez a README architektúra-diagramjának "MATCH" döntési
  pontja.

### Enrollment (hangprofil-regisztráció)
- **Általános jelentés:** Az a folyamat, amikor egy adott személy hangjából
  mintát veszünk, és elmentjük a referencia-embeddingjét, hogy a rendszer
  később felismerje.
- **Hol jelenik meg a projektben:** `POST /v1/speakers` végpont
  (`app/api/speakers.py`), `SpeakerProfileStore` interfész,
  `SpeakerProfile` séma.
- **Mit old meg a projektben:** Ez teszi lehetővé, hogy a diarizáció
  anonim "SPEAKER_00" jelölése helyett a leiratban valódi kollégák neve
  jelenjen meg.

### Futó átlag (running average) az enrollmentnél
- **Általános jelentés:** Egy érték folyamatos finomítása új mérésekkel,
  ahelyett hogy az utolsó mérés felülírná a korábbiakat — az új és a régi
  érték súlyozott keverékét tartjuk meg.
- **Hol jelenik meg a projektben:** `app/core/enrollment/store.py` —
  ismételt regisztráció ugyanarra a névre az embeddinget **finomítja**,
  nem felülírja.
- **Mit old meg a projektben:** Több, rövidebb hangfelvételből
  pontosabb, stabilabb hangprofil épül fel idővel, mint egyetlen mintából.

---

## 5. Beszédfelismerés (ASR)

### ASR (Automatic Speech Recognition, automatikus beszédfelismerés)
- **Általános jelentés:** Az a technológia/modell, amely hangot szöveggé
  alakít ("mit mondott a beszélő").
- **Hol jelenik meg a projektben:** `AsrClient` interfész
  (`app/core/interfaces.py`), `ASR_BACKEND`, `ASR_ENDPOINT_URL` config.
- **Mit old meg a projektben:** Ez adja a leirat *szövegét* — a diarizáció
  csak azt mondja meg, *ki mikor* beszélt, az ASR mondja meg, *mit*.

### Whisper / Whisper API dialektus
- **Általános jelentés:** Az OpenAI "Whisper" nevű beszédfelismerő
  modellje, és az ehhez tartozó, széles körben átvett HTTP API-forma
  (`POST /audio/transcriptions`, multipart `file` + `model` mező).
- **Hol jelenik meg a projektben:** `ASR_BACKEND=openai_compatible`
  alapértelmezett, `ASR_MODEL=whisper-large-v3`.
- **Mit old meg a projektben:** A projekt **soha nem futtat** ASR-modellt
  magában — csak ezt a de facto szabvány API-formát beszéli egy külső
  végponttal, ami miatt bármikor lecserélhető a mögötte futó konkrét modell
  anélkül, hogy a worker kódját módosítani kellene.

### Modell-agnosztikus (model-agnostic) dizájn
- **Általános jelentés:** Olyan rendszertervezési elv, ahol a rendszer nem
  köti magát egyetlen konkrét (gépi tanulási) modellhez — a modell csak egy
  kicserélhető, konfigurálható komponens.
- **Hol jelenik meg a projektben:** A README fő tervezési elve; minden
  `*_BACKEND` env-változó (`ASR_BACKEND`, `VAD_BACKEND`,
  `DIARIZATION_BACKEND`, `EMBEDDING_BACKEND`).
- **Mit old meg a projektben:** Amikor egy jobb ASR/diarizációs modell
  jelenik meg a piacon, elég egy config-változtatás, nem kell a workert
  újraírni vagy újra deployolni kóddal.

### Generic backend / mező-map-elés (field mapping)
- **Általános jelentés:** Konfigurációval (nem kóddal) leírni, hogy egy
  külső API kérésének/válaszának mely mezői felelnek meg a saját belső
  adatszerkezetünk mezőinek.
- **Hol jelenik meg a projektben:** `ASR_BACKEND=generic`,
  `GENERIC_AUDIO_FIELD`, `GENERIC_RESPONSE_TEXT_PATH`,
  `GENERIC_RESPONSE_SEGMENTS_PATH` (`app/config.py`,
  `app/core/asr/generic.py`).
- **Mit old meg a projektben:** Ha egy ASR-végpont nem a Whisper-dialektust
  beszéli, így is bárhogy bekötheti egy config-fájl, kód írása nélkül.

### Konfidencia (confidence score)
- **Általános jelentés:** Egy 0–1 közti szám, amely megmutatja, mennyire
  "biztos" a modell a saját kimenetében.
- **Hol jelenik meg a projektben:** `AsrResult.confidence`,
  `TranscriptSegment.asr_confidence`, `SpeakerLabel.confidence`
  (`app/schemas.py`).
- **Mit old meg a projektben:** Lehetővé teszi a fogyasztó (pl. UI)
  számára, hogy megkülönböztesse a biztos és a bizonytalan
  szövegrészeket/beszélő-hozzárendeléseket.

---

## 6. API-tervezés és webes protokollok

### REST / REST API
- **Általános jelentés:** Egy elterjedt architektúra-stílus webes
  API-khoz, ahol erőforrásokat (pl. "egy leirat", "egy beszélő") HTTP
  metódusokkal (GET, POST, DELETE...) és URL-ekkel kezelünk.
- **Hol jelenik meg a projektben:** `/v1/transcribe`, `/v1/speakers`,
  `/v1/health` stb. végpontok (`app/api/`).
- **Mit old meg a projektben:** Egyszerű, szabványos, bármilyen kliensből
  (curl, más szolgáltatás, UI) hívható interfészt ad a workerhez.

### HTTP metódusok (GET, POST, DELETE)
- **Általános jelentés:** A HTTP-kérés "igéje", amely jelzi a szándékot:
  GET = adat lekérése, POST = új adat létrehozása/feldolgozás indítása,
  DELETE = adat törlése.
- **Hol jelenik meg a projektben:** `POST /v1/transcribe` (leiratozás
  indítása), `GET /v1/speakers` (lista lekérése), `DELETE /v1/speakers/{id}`
  (profil törlése).
- **Mit old meg a projektben:** Egyértelműsíti a végpontok szándékát a
  hívó fél számára, szabványos HTTP-eszközökkel (pl. cache-elés GET-nél).

### Multipart/form-data
- **Általános jelentés:** Egy HTTP kéréstest-formátum, amely bináris
  fájlokat és szöveges mezőket egyszerre tud egy kérésben elküldeni.
- **Hol jelenik meg a projektben:** `POST /v1/transcribe` (`file` mező),
  `POST /v1/speakers` (`name` + `audio` mező), `python-multipart` csomag.
- **Mit old meg a projektben:** Ez a szabványos módja annak, hogy egy
  hangfájlt egy HTTP-kérésben feltöltsünk egy REST végpontra.

### Query paraméter
- **Általános jelentés:** Az URL-hez `?kulcs=érték` formában csatolt,
  opcionális beállítás egy kéréshez.
- **Hol jelenik meg a projektben:** `GET /v1/transcribe?format=srt|vtt`,
  `min_speakers`/`max_speakers`/`language` opcionális paraméterek.
- **Mit old meg a projektben:** Lehetővé teszi, hogy ugyanaz a végpont
  többféle kimeneti formátumot vagy finomhangolást adjon anélkül, hogy
  külön végpontot kellene írni mindegyikhez.

### WebSocket
- **Általános jelentés:** Egy HTTP-ből "felfejlesztett" (upgrade-elt),
  tartós, kétirányú kapcsolat kliens és szerver közt — mindkét fél
  bármikor küldhet üzenetet, nem csak kérés-válasz párban, mint a
  hagyományos HTTP-nél.
- **Hol jelenik meg a projektben:** `WS /v1/transcribe/stream`
  (`app/api/stream.py`), `websockets` csomag.
- **Mit old meg a projektben:** Ez teszi lehetővé az élő (streaming)
  módot — a kliens folyamatosan küldheti a hang-chunkokat, a szerver pedig
  köztes ("partial") és végleges ("final") eredményeket küldhet vissza,
  anélkül, hogy minden chunkhoz új HTTP-kérést kellene nyitni.

### JSON (JavaScript Object Notation)
- **Általános jelentés:** Egy szöveges, ember és gép által is
  könnyen olvasható adatcsere-formátum (kulcs–érték páros objektumok,
  listák, alaptípusok).
- **Hol jelenik meg a projektben:** A `Transcript`, `StreamEvent` kimeneti
  sémák (`app/schemas.py`), a `/v1/config` válasz.
- **Mit old meg a projektben:** Szabványos, nyelv-független módja annak,
  hogy a leiratot bármilyen fogyasztó (más program, UI) fel tudja
  dolgozni.

### SRT / WebVTT
- **Általános jelentés:** Két szabványos **feliratfájl-formátum**
  (SubRip / Web Video Text Tracks) videó/hanglejátszókhoz — időbélyeggel
  ellátott szövegblokkok.
- **Hol jelenik meg a projektben:** `GET /v1/transcribe?format=srt|vtt`,
  `app/utils/export.py`.
- **Mit old meg a projektben:** A saját JSON-séma mellett szabványos
  feliratformátumot is ad, hogy a leirat bármilyen meglévő videólejátszó/
  szerkesztő eszközzel is használható legyen, nem csak a saját API-t ismerő
  kóddal.

---

## 7. Backend-architektúra és tervezési minták

### Interfész / absztrakt osztály (abstract base class)
- **Általános jelentés:** Egy "szerződés", amely leírja, milyen
  metódusokat *kell* implementálnia egy komponensnek, anélkül hogy
  meghatározná, *hogyan*. Pythonban ezt az `abc` modul `ABC` osztályával
  és `@abstractmethod` dekorátorral fejezik ki.
- **Hol jelenik meg a projektben:** `app/core/interfaces.py` —
  `VoiceActivityDetector`, `Diarizer`, `EmbeddingExtractor`, `AsrClient`,
  `SpeakerProfileStore`.
- **Mit old meg a projektben:** A pipeline-kód (`pipeline.py`,
  `streaming_pipeline.py`) *soha* nem a konkrét (pl. pyannote) megoldást
  hívja, csak az interfészt — ez teszi lehetővé a modell-agnosztikus,
  cserélhető architektúrát.

### Factory (gyár mintázat)
- **Általános jelentés:** Egy tervezési minta: egy függvény/osztály,
  amely — jellemzően konfiguráció alapján — eldönti és létrehozza, *melyik*
  konkrét implementációt kell használni, elrejtve ezt a döntést a hívó elől.
- **Hol jelenik meg a projektben:** `app/core/asr/factory.py` — a
  `ASR_BACKEND` env-változó alapján dönti el, `OpenAICompatibleAsrClient`
  vagy `GenericAsrClient` induljon.
- **Mit old meg a projektben:** A többi kód (pl. az API réteg) nem kell,
  hogy tudja, melyik konkrét ASR-kliens fut — csak az interfészt kapja meg,
  amit a factory állított elő a config alapján.

### Config-vezérelt (config-driven) dizájn
- **Általános jelentés:** Olyan rendszer, ahol a viselkedést
  (melyik modellt/backendet használjuk, milyen küszöbértékekkel)
  beállításokból (env-változó, YAML) vezéreljük, nem forráskód-módosítással.
- **Hol jelenik meg a projektben:** `app/config.py` — minden `*_BACKEND`,
  küszöbérték (pl. `EMBEDDING_SIMILARITY_THRESHOLD`), időzítés
  (`STREAMING_*`).
- **Mit old meg a projektben:** Egy modell/backend cseréje vagy egy
  paraméter finomhangolása nem igényel kódmódosítást vagy újra-buildelést,
  csak env-változó- vagy YAML-módosítást.

### Adatkontraktus / séma-verziózás (schema versioning)
- **Általános jelentés:** A kimeneti adatformátum explicit verziószámmal
  jelölése, hogy a fogyasztók tudják, mikor változott a struktúra
  visszafelé-nem-kompatibilis módon.
- **Hol jelenik meg a projektben:** `SCHEMA_VERSION = "1.0"`,
  `Transcript.schema_version` (`app/schemas.py`).
- **Mit old meg a projektben:** A README explicit kimondja: ez az
  **egyetlen dolog**, amire egy külső fogyasztó (pl. `meeting-recorder`)
  szabad, hogy támaszkodjon — a belső kód szabadon változhat, amíg ez a
  séma stabil marad.

### Laza csatolás (loose coupling)
- **Általános jelentés:** Két komponens úgy működik együtt, hogy minél
  kevesebbet "tudnak" egymás belső részleteiről — csak egy jól definiált
  interfészen (itt: a JSON/HTTP-kontraktuson) keresztül érintkeznek.
- **Hol jelenik meg a projektben:** A README kimondja: a worker "Semmit
  nem tud arról, honnan jött a hang" — nincs Jitsi/WebRTC-specifikus kód
  benne.
- **Mit old meg a projektben:** Ez teszi lehetővé, hogy a komponens
  bármilyen hívó szolgáltatásba (meeting-recorder, élő bot, batch-feldolgozó)
  bekötve, azok belső működésének ismerete nélkül újrahasználható legyen.

---

## 8. Aszinkron programozás (Python `asyncio`)

### Aszinkron (async) függvény / `async`/`await`
- **Általános jelentés:** Olyan függvény, amely futása közben "átadhatja a
  vezérlést" más feladatoknak, amíg egy lassú műveletre (pl. hálózati
  hívásra) várakozik, helyette blokkolás nélkül.
- **Hol jelenik meg a projektben:** `AsrClient.transcribe` metódus
  `async def`-ként van deklarálva; `app/api/*.py` FastAPI-végpontjai.
- **Mit old meg a projektben:** Amíg egy ASR-hívás a hálózaton "úton van",
  a szerver más kéréseket is tud kezelni ugyanazon a folyamaton belül.

### Event loop
- **Általános jelentés:** Az aszinkron futtatási modell "motorja", amely
  eldönti, melyik várakozó feladat futhat tovább, amikor egy másik éppen
  I/O-ra (hálózat, fájl) vár.
- **Hol jelenik meg a projektben:** A README explicit említi: "egy lassú
  diarizáció ne blokkolja a FastAPI event loopot más egyidejű kérések
  elől".
- **Mit old meg a projektben:** Ez az oka annak, hogy a blokkoló
  (szinkron) hívásokat külön szálra kell kitenni (ld. `asyncio.to_thread`)
  — különben egyetlen lassú kérés az egész szervert "megfagyasztaná".

### `asyncio.gather`
- **Általános jelentés:** Több aszinkron feladat **párhuzamos** indítása,
  és az összes eredményére való együttes várakozás.
- **Hol jelenik meg a projektben:** README: "Batch módban minden
  diarizált szegmens embeddingje és ASR-hívása **párhuzamosan** fut
  (`asyncio.gather`)".
- **Mit old meg a projektben:** Ha egy felvételben 5 beszélő-szegmens van,
  nem egymás után, hanem egyszerre kerülnek elküldésre az ASR-végpontnak —
  ez lerövidíti a teljes feldolgozási időt.

### `asyncio.to_thread`
- **Általános jelentés:** Egy szinkron (blokkoló), CPU-igényes függvény
  háttérszálon való futtatása, hogy az aszinkron event loop közben más
  feladatokat is tudjon kezelni.
- **Hol jelenik meg a projektben:** README: "a blokkoló CPU/GPU-hívások
  (`vad.detect`, `diarizer.diarize`, `embedder.embed`) `asyncio.to_thread`-del
  kerülnek háttérszálra".
- **Mit old meg a projektben:** A diarizációs/embedding modellek (torch,
  pyannote) szinkron, CPU/GPU-terhelő Python-kódot futtatnak — ezek
  event loopon belüli direkt hívása blokkolná az egész szervert; a
  háttérszálra kitevés ezt elkerüli.

### Konkurrencia (concurrency) vs. párhuzamosság (parallelism)
- **Általános jelentés:** Konkurrencia = több feladat *átlapolva*
  halad (nem feltétlenül egyszerre futva, pl. I/O-várakozás közben);
  párhuzamosság = tényleg egyszerre, több CPU-magon/szálon fut.
- **Hol jelenik meg a projektben:** `ASR_REQUEST_CONCURRENCY` /
  `request_concurrency` config (`app/config.py`) — a max. egyidejű,
  folyamatban lévő ASR-kérések száma.
- **Mit old meg a projektben:** Korlátozza, hány szegmens ASR-hívása
  lehet egyszerre "úton" a külső végponthoz, hogy ne terheljük túl azt
  (pl. rate-limit vagy erőforrás-védelem miatt).

---

## 9. Webkeretrendszer és adatvalidáció (FastAPI, Pydantic)

### FastAPI
- **Általános jelentés:** Egy modern Python webkeretrendszer REST/
  WebSocket API-k építésére, beépített aszinkron támogatással és
  automatikus adatvalidációval (Pydantic-tal együtt).
- **Hol jelenik meg a projektben:** `app/main.py`, `app/api/*.py`,
  `fastapi==0.115.0` a `requirements.txt`-ben.
- **Mit old meg a projektben:** Ez adja a HTTP/WebSocket-réteget — a
  végpontok routolását, a kérés/válasz validációt, a dokumentált API-t —
  anélkül, hogy ezt a projektnek kézzel kellene megírnia.

### Uvicorn / ASGI szerver
- **Általános jelentés:** Egy Python "ASGI" (Asynchronous Server Gateway
  Interface) szerver, amely tényleges hálózati kéréseket fogad, és
  aszinkron Python-alkalmazásoknak (mint a FastAPI) továbbítja.
- **Hol jelenik meg a projektben:** `Dockerfile` `CMD` sora:
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.
- **Mit old meg a projektben:** Ez futtatja ténylegesen a FastAPI-alkalmazást
  — nélküle a Python-kód csak definíció lenne, nem futó hálózati szolgáltatás.
  A `--workers 1` azért fontos, mert a diarizációs/embedding modellek
  process-indításkor egyszer töltődnek be memóriába (ld. 11. szakasz,
  "Konténer-replikák").

### Pydantic / `BaseModel`
- **Általános jelentés:** Egy Python könyvtár, amely típus-annotációk
  alapján automatikusan validálja és szerializálja/deszerializálja
  adatstruktúrákat (pl. JSON ↔ Python objektum).
- **Hol jelenik meg a projektben:** Minden séma-osztály (`Transcript`,
  `SpeakerLabel`, `StreamEvent`...) a `pydantic.BaseModel`-ből származik
  (`app/schemas.py`).
- **Mit old meg a projektben:** Garantálja, hogy a kimeneti JSON mindig a
  deklarált struktúrának megfelel (pl. `confidence` mindig 0–1 közti szám),
  és automatikusan hibát dob, ha valami nem felel meg az elvárt típusnak.

### Pydantic Settings (`pydantic-settings`, `BaseSettings`)
- **Általános jelentés:** A Pydantic egy kiegészítése, amely a
  konfigurációt (env-változók, `.env` fájl) automatikusan Python-objektummá
  alakítja, típusellenőrzéssel.
- **Hol jelenik meg a projektben:** `app/config.py` — `ASRSettings`,
  `VADSettings` stb., `env_prefix` (pl. `"ASR_"`).
- **Mit old meg a projektben:** Nem kell kézzel `os.environ`-ból
  kiolvasni és típusra konvertálni minden beállítást — a `Settings`
  osztályok ezt automatikusan, típusbiztosan teszik meg, és validálják is
  (pl. hogy `EMBEDDING_SIMILARITY_THRESHOLD` 0 és 1 között legyen).

### YAML konfigurációs fájl
- **Általános jelentés:** Egy ember által is könnyen olvasható,
  strukturált konfigurációs fájlformátum (behúzás-alapú, JSON-nál
  olvashatóbb szintaxis).
- **Hol jelenik meg a projektben:** `CONFIG_FILE` env-változó
  (`app/config.py`, `_load_yaml_overrides`), `pyyaml` csomag.
- **Mit old meg a projektben:** Alternatívát ad a sok különálló
  env-változó helyett egy közös, verziózható konfigurációs fájlhoz —
  env-változó mindig felülírja, ha mindkettő megvan.

---

## 10. Megfigyelhetőség (observability)

### Strukturált naplózás (structured logging)
- **Általános jelentés:** Naplóüzenetek gépileg feldolgozható formátumban
  (jellemzően JSON) kiírása, szabad szöveg helyett — így kereshetők,
  szűrhetők, aggregálhatók egy log-gyűjtő rendszerben.
- **Hol jelenik meg a projektben:** `app/observability.py` —
  `_JsonFormatter`, `configure_logging`.
- **Mit old meg a projektben:** Éles (production) üzemeltetésnél a
  logokat automatikus eszközök (pl. log-aggregátor) dolgozzák fel — a
  JSON-formátum ezt könnyebbé teszi, mint a szabad szöveges log-sorok.

### Prometheus / metrika (metrics)
- **Általános jelentés:** A Prometheus egy elterjedt, nyílt forráskódú
  monitorozó rendszer, amely rendszeresen "lekérdezi" (scrape-eli) a
  szolgáltatásoktól a saját, számszerű állapotukat (kérésszám, válaszidő...).
- **Hol jelenik meg a projektben:** `GET /metrics` végpont,
  `prometheus_client` csomag, `REQUEST_COUNTER`, `PIPELINE_LATENCY`
  (`app/observability.py`).
- **Mit old meg a projektben:** Lehetővé teszi, hogy egy külső
  monitorozó rendszer láthassa, hány kérés futott le, és mennyi ideig
  tartott a pipeline egyes szakaszainak feldolgozása — ez alapján
  riasztás/dashboard állítható be.

### Counter / Histogram (metrika-típusok)
- **Általános jelentés:** A Prometheus két alap metrika-típusa: a
  **Counter** egy csak növekvő számláló (pl. "összes kérés száma"), a
  **Histogram** értékek eloszlását méri idő/méret-tartományokba
  sorolva (pl. "hány kérés futott 0-1s, 1-2s... alatt").
- **Hol jelenik meg a projektben:** `REQUEST_COUNTER = Counter(...)`,
  `PIPELINE_LATENCY = Histogram(...)` (`app/observability.py`).
- **Mit old meg a projektben:** A Histogram teszi lehetővé, hogy ne csak
  az átlagos válaszidőt lássuk, hanem azt is, hány kérés volt lassú
  "kiugró" érték (pl. p95/p99 latencia számolható belőle).

### Liveness probe / Readiness probe
- **Általános jelentés:** Két különböző "egészség-ellenőrzés" egy
  szolgáltatáson: a **liveness** azt kérdezi, "él-e még a folyamat"
  (ha nem, újraindítandó), a **readiness** azt, "kész-e már *kérések
  fogadására*" (pl. betöltötte-e már a szükséges modelleket).
- **Hol jelenik meg a projektben:** `GET /v1/health` (liveness),
  `GET /v1/ready` (readiness, 503-at ad, amíg a modellek nem töltődtek be).
- **Mit old meg a projektben:** Kubernetes/orchesztrátor rendszerek ez
  alapján döntik el, mikor küldjenek forgalmat egy konténerhez (readiness),
  és mikor indítsák újra, ha "beragadt" (liveness) — a README explicit
  "k8s rolling deploy"-t említ ok-ként.

---

## 11. Konténerizáció és üzemeltetés (Docker)

### Konténer (container) / Docker image
- **Általános jelentés:** Egy konténer egy futó, elszigetelt
  folyamat-környezet, amely egy **image**-ből (egy előre becsomagolt,
  a futáshoz szükséges összes függőséget tartalmazó "sablonból") indul.
- **Hol jelenik meg a projektben:** `Dockerfile`, `docker-compose.yml`,
  README: "Dockerben konténerizált, modell-agnosztikus mikroszolgáltatás".
- **Mit old meg a projektben:** Garantálja, hogy a worker ugyanazokkal a
  függőségekkel (Python-verzió, ffmpeg, torch stb.) fusson bármilyen
  gépen — a fejlesztői laptopon éppúgy, mint egy éles szerveren.

### Többlépcsős build (multi-stage build)
- **Általános jelentés:** Egy Dockerfile-technika, ahol több
  egymásra épülő "szakaszban" (`FROM ... AS <név>`) épül fel az image, és
  csak a legutolsó szakasz kerül a végleges, futtatott image-be — a
  build-only eszközök (pl. fordítók) nem terhelik a végeredményt.
- **Hol jelenik meg a projektben:** `Dockerfile` — `base` → `deps` →
  `runtime` szakaszok; a `gcc`/`python3-dev` csak a `deps` szakaszban
  települ, a végleges image-be nem kerül be.
- **Mit old meg a projektben:** Kisebb, biztonságosabb végleges image
  (nincs benne fordító-eszköztár), miközben a `webrtcvad` natív
  kiterjesztésének fordításához szükséges eszközök is elérhetők
  build-időben.

### Volume (kötet)
- **Általános jelentés:** Egy tárolóterület, amely a konténer
  élettartamán *túl* is megmarad (perzisztens), és a konténerhez
  kapcsolható/csatolható.
- **Hol jelenik meg a projektben:** `speaker-profiles`, `hf-cache`
  Docker-volume-ok (`docker-compose.yml`), `ENROLLMENT_STORE_PATH`,
  `HF_HOME`.
- **Mit old meg a projektben:** A regisztrált hangprofilok és a letöltött
  (több GB-os) modellsúlyok **nem tűnnek el**, amikor egy konténer
  újraindul vagy újra deploy-olódik.

### Healthcheck
- **Általános jelentés:** Egy beépített, a konténer-motor (Docker/k8s)
  által rendszeresen futtatott ellenőrző parancs, amely eldönti, "egészséges"
  -e még a konténer.
- **Hol jelenik meg a projektben:** `Dockerfile` `HEALTHCHECK` sora,
  `docker-compose.yml` `healthcheck:` blokk — mindkettő a `/v1/health`
  végpontot hívja `curl`-lal.
- **Mit old meg a projektben:** Automatikusan jelzi, ha a worker
  folyamata "beragadt" — orchesztrátor-eszközök ez alapján tudják
  újraindítani.

### docker-compose
- **Általános jelentés:** Egy eszköz/konfigurációs fájl-formátum
  (`docker-compose.yml`), amellyel több összetartozó konténer (itt:
  a worker + egy mock ASR-szerver) egyszerre, egymáshoz kötve indítható.
- **Hol jelenik meg a projektben:** `docker-compose.yml` — `worker` +
  `mock-asr` szolgáltatások.
- **Mit old meg a projektben:** Egyetlen paranccsal (`docker compose up
  --build`) elindítható a teljes demó-környezet — a worker és egy hamis
  ASR-végpont —, valódi GPU vagy modell nélkül is kipróbálható a teljes
  pipeline.

### Horizontális skálázás / replika (replica)
- **Általános jelentés:** Egy szolgáltatás terhelésének kezelése úgy, hogy
  *több, egymással azonos, egymástól független példányt* (replikát)
  indítunk el (ellentétben a "vertikális" skálázással, ami egyetlen
  példányt tesz nagyobbá).
- **Hol jelenik meg a projektben:** README "Skálázhatóság" szakasz,
  `docker-compose.yml` `deploy.replicas`.
- **Mit old meg a projektben:** A README kimondja: a diarizációs/embedding
  modell egyszer töltődik be egy konténer-folyamatba (ezért `--workers 1`);
  a terhelés növelésére nem in-process worker-számot növelünk, hanem
  **konténer-replikákat** indítunk — GPU esetén ez kerüli el, hogy több
  folyamat egy GPU memóriáját "túltöltse" (OOM — Out Of Memory hiba).

### Load balancer
- **Általános jelentés:** Egy komponens, amely a beérkező kéréseket
  szétosztja több, azonos szolgáltatás-replika között.
- **Hol jelenik meg a projektben:** README architektúra-diagram:
  "Load balancer / k8s probe / Prometheus scraper" → health/metrics
  végpontok.
- **Mit old meg a projektben:** Ha több worker-replika fut, a load
  balancer dönti el, melyik replika kapja meg az adott kérést — ehhez
  használja a liveness/readiness probe-okat is, hogy csak egészséges
  replikákhoz irányítson forgalmat.

---

## 12. Gépi tanulás / GPU-üzemeltetés

### HuggingFace / HuggingFace Hub
- **Általános jelentés:** Egy online platform és Python-ökoszisztéma,
  ahol előre betanított gépi tanulási modellek ("model weights") tölthetők
  le és oszthatók meg.
- **Hol jelenik meg a projektben:** `DIARIZATION_HF_TOKEN`,
  `EMBEDDING_HF_TOKEN`, `HF_HOME` env-változók; `pyannote/
  speaker-diarization-3.1`, `pyannote/embedding` modellnevek.
- **Mit old meg a projektben:** Innen tölti le a rendszer a
  diarizációs/embedding modellek súlyait, ahelyett hogy a projekt saját
  magának kellene tréningeznie/tárolnia azokat.

### Gated model (zárolt/engedélyköteles modell)
- **Általános jelentés:** Egy HuggingFace-en elérhető modell, amelynek
  letöltéséhez a felhasználónak előbb el kell fogadnia egy
  licencfeltételt a HuggingFace weboldalán, és be kell jelentkeznie egy
  hozzáférési tokennel (`HF_TOKEN`).
- **Hol jelenik meg a projektben:** README: "a `pyannote/
  speaker-diarization-3.1` és a `pyannote/embedding` gated modellek,
  licenc-elfogadás szükséges a HF oldalon".
- **Mit old meg a projektben:** Ez magyarázza, miért kell
  `DIARIZATION_HF_TOKEN`/`EMBEDDING_HF_TOKEN` beállítani éles használat
  előtt — anélkül a modell letöltése sikertelen lenne.

### CPU vs. GPU / CUDA
- **Általános jelentés:** A CPU (Central Processing Unit) általános célú
  processzor; a GPU (Graphics Processing Unit) sok, párhuzamos
  számításra optimalizált mag — a mély tanulási modellek futtatásában
  sokszorosan gyorsabb. A CUDA az NVIDIA GPU-k programozási platformja,
  amit a PyTorch (torch) is használ.
- **Hol jelenik meg a projektben:** `DIARIZATION_DEVICE`,
  `EMBEDDING_DEVICE` (`cpu`/`cuda`), `TORCH_INDEX_URL` build-arg a
  `Dockerfile`-ban.
- **Mit old meg a projektben:** Alapból CPU-wheel-lel épül az image
  (nincs szükség GPU-s host-ra a kipróbáláshoz); éles, nagy terhelésű
  használatnál GPU-ra kapcsolható a diarizáció/embedding gyorsításáért.

### PyTorch (torch)
- **Általános jelentés:** Egy széles körben használt, nyílt forráskódú
  gépi tanulási keretrendszer (könyvtár) neurális hálók építésére és
  futtatására.
- **Hol jelenik meg a projektben:** `torch==2.4.1`, `torchaudio==2.4.1` a
  `requirements.txt`-ben — a `pyannote.audio` és `speechbrain` mindkettő
  ezen alapul.
- **Mit old meg a projektben:** Ez a "motor", ami alatt a diarizációs és
  embedding neurális hálók tényleges számításai futnak.

### Modellsúlyok (model weights)
- **Általános jelentés:** Egy betanított neurális háló belső, számszerű
  paraméterei — ezek tárolása/betöltése teszi lehetővé, hogy a modellt
  ne kelljen újra betanítani minden használat előtt.
- **Hol jelenik meg a projektben:** `HF_HOME=/data/hf-cache` — README:
  "perzisztálja a letöltött modellsúlyokat (diarizáció + embedding)
  konténer-újraindítások között".
- **Mit old meg a projektben:** Elkerüli, hogy minden konténer-indításnál
  újra le kelljen tölteni a több gigabájtos modelleket.

### OOM (Out Of Memory)
- **Általános jelentés:** Egy hibaállapot, amikor egy folyamat több
  memóriát (RAM vagy GPU-memóriát) próbál használni, mint amennyi
  rendelkezésre áll — ilyenkor a folyamat jellemzően összeomlik.
- **Hol jelenik meg a projektben:** README: "GPU-n több folyamat egy
  GPU-ra töltve OOM-olna" — ezért `--workers 1` és konténer-replikákkal
  skálázás, nem in-process worker-számmal.
- **Mit old meg a projektben:** Ez az indoka annak, hogy miért nem
  szabad egyetlen GPU-ra több modell-másolatot betölteni egy konténeren
  belül.

---

## 13. Tesztelés és minőségbiztosítás

### Unit teszt (egységteszt)
- **Általános jelentés:** Egy kódrészlet (jellemzően egyetlen függvény
  vagy osztály) önálló, más komponensektől elszigetelt tesztelése.
- **Hol jelenik meg a projektben:** `tests/` mappa — `test_schemas.py`,
  `test_config.py`, `test_audio_export.py` stb.; `pytest` futtatja.
- **Mit old meg a projektben:** Gyorsan (nehéz ML-függőségek, torch/
  pyannote/speechbrain/webrtcvad nélkül) ellenőrzi, hogy a séma, a config,
  az export-logika, az enrollment-tároló és a koszinusz-hasonlóság
  számítás helyesen működik — ez futhat gyorsan CI-ban is.

### pytest
- **Általános jelentés:** A Python legelterjedtebb teszt-futtató
  keretrendszere.
- **Hol jelenik meg a projektben:** `pytest tests/ -q` parancs a
  README "Fejlesztés / tesztelés" szakaszában.
- **Mit old meg a projektben:** Ez futtatja le és jelenti az egységteszt-
  eredményeket a fejlesztőnek/CI-nak.

### CI (Continuous Integration, folyamatos integráció)
- **Általános jelentés:** Egy automatizált folyamat, amely minden
  kódváltozás után automatikusan lefuttatja a teszteket (és esetleg más
  ellenőrzéseket), hogy korán kiderüljön, ha valami elromlott.
- **Hol jelenik meg a projektben:** README: "ezek CI-ban gyorsan futnak" —
  a "nehéz" ML-tesztek explicit **nincsenek** a gyors CI-tesztek közt.
- **Mit old meg a projektben:** Elválasztja a gyorsan futó, függőség-
  mentes egységteszteket a lassú, GPU-t/valódi HF-tokent igénylő
  end-to-end ML-teszteléstől, hogy a CI gyors és megbízható maradjon.

### Mock (hamisított/utánzott komponens)
- **Általános jelentés:** Egy valódi komponenst helyettesítő, egyszerűsített
  "hamis" implementáció, amelyet teszteléshez/demózáshoz használunk, mert
  a valódi verzió túl lassú, drága, vagy nem elérhető.
- **Hol jelenik meg a projektben:** `examples/mock_asr_server` —
  egy hamis ASR-végpont, amit a `docker-compose.yml` a `mock-asr`
  szolgáltatásként indít.
- **Mit old meg a projektben:** Lehetővé teszi, hogy a teljes pipeline
  végigfusson GPU vagy valódi ASR-modell nélkül is — pl. bemutatáshoz
  vagy gyors kipróbáláshoz.

### WER / CER (Word Error Rate / Character Error Rate)
- **Általános jelentés:** Standard metrikák egy beszédfelismerő
  kimenetének minőség-mérésére: hány szó/karakter hibás (hozzáadott,
  kihagyott, felcserélt) a referencia (helyes) szöveghez képest.
- **Hol jelenik meg a projektben:** `eval/metrics.py`,
  `eval/run_comparison.py` — README: "WER/CER **és** beszélő-attribúciós
  pontosság mérhető".
- **Mit old meg a projektben:** Objektív, számszerű módot ad arra, hogy
  összehasonlítsuk különböző ASR-modellek/beállítások minőségét ugyanazon
  a teszt-hanganyagon.

---

## 14. Egyéb, gyakran előforduló fogalmak

### Env-változó (environment variable)
- **Általános jelentés:** Egy operációs rendszer szintű, kulcs-érték
  páros beállítás, amelyet egy futó folyamat elérhet (pl. `os.environ`-on
  keresztül Pythonban).
- **Hol jelenik meg a projektben:** `.env.example`, `.env` fájl,
  minden `ASR_*`, `VAD_*`, `DIARIZATION_*` stb. beállítás.
- **Mit old meg a projektben:** A titkos adatokat (pl. `HF_TOKEN`,
  `API_KEY`) és a környezetfüggő beállításokat elválasztja a kódtól —
  ugyanaz az image más-más `.env`-vel más környezetben (dev/staging/prod)
  futhat.

### `.env` fájl
- **Általános jelentés:** Egy egyszerű szöveges fájl `KULCS=érték`
  sorokkal, amelyet a program indításkor beolvas, és a benne lévő
  értékeket env-változóként kezeli.
- **Hol jelenik meg a projektben:** `.env.example` → `cp .env.example
  .env` (README "Gyors indítás").
- **Mit old meg a projektben:** Egy helyen tartja a lokális/demó
  konfigurációt, anélkül hogy titkos adatokat kódba kellene írni.

### API-kulcs (API key)
- **Általános jelentés:** Egy titkos azonosító-token, amellyel egy
  kliens autentikálja magát egy külső API felé.
- **Hol jelenik meg a projektben:** `ASR_API_KEY` (`app/config.py`,
  `ASRSettings.api_key`) — a külső ASR-végponthoz való hitelesítéshez.
- **Mit old meg a projektben:** Ha a külső ASR-szolgáltatás
  hitelesítést vár (pl. egy felhő-alapú Whisper API), ezzel küldi el a
  worker a hitelesítő adatot minden kéréshez.

### Redaktálás (redaction, titkok elrejtése)
- **Általános jelentés:** Érzékeny adatok (jelszavak, tokenek, kulcsok)
  automatikus kitakarása/elrejtése egy kimenetben, mielőtt azt bárki
  máshoz eljuttatnánk.
- **Hol jelenik meg a projektben:** `GET /v1/config` végpont — README:
  "Aktuális (titkok nélkül redaktált) konfiguráció".
- **Mit old meg a projektben:** Lehetővé teszi, hogy egy admin/debug
  célú végpont megmutassa a futó konfigurációt anélkül, hogy pl. a
  `HF_TOKEN` vagy `ASR_API_KEY` értéke kiszivárogna a válaszban.

### NFS / EFS (megosztott hálózati tárolás)
- **Általános jelentés:** Hálózaton keresztül elérhető fájlrendszerek
  (Network File System / Amazon Elastic File System), amelyeket több,
  különböző gépen futó folyamat is egyszerre, közösen elérhet.
- **Hol jelenik meg a projektben:** README "Skálázhatóság" szakasz —
  "megosztott hálózati volume (NFS/EFS-szerű, azonos
  `ENROLLMENT_STORE_PATH` minden replikán)".
- **Mit old meg a projektben:** A jelenlegi fájl-alapú
  `SpeakerProfileStore` több konténer-replika esetén csak akkor látja
  ugyanazokat a regisztrált hangprofilokat, ha mindegyik replika ugyanazt
  a megosztott hálózati tárolót éri el — ez az egy-replikán-túli skálázás
  jelenlegi korlátja és megoldási iránya.

### Kubernetes (k8s) / rolling deploy
- **Általános jelentés:** A Kubernetes egy elterjedt konténer-
  orchesztrátor rendszer, amely konténerek indítását, skálázását,
  egészség-figyelését automatizálja. A "rolling deploy" egy frissítési
  stratégia, amely fokozatosan, egyszerre csak néhány replikát cserél le
  újra, hogy a szolgáltatás közben is elérhető maradjon.
- **Hol jelenik meg a projektben:** README: "`GET /v1/ready` (readiness,
  külön a liveness-től — **k8s rolling deploy**-hoz)".
- **Mit old meg a projektben:** A readiness probe elválasztása a
  liveness-től teszi lehetővé, hogy egy Kubernetes-fürt fokozatos
  frissítés közben csak azokra a replikákra irányítson forgalmat,
  amelyek már valóban kész állapotban vannak (betöltött modellekkel).

### ISO-639-1
- **Általános jelentés:** Egy szabványos, kétbetűs nyelvkód-lista
  (pl. `hu` = magyar, `en` = angol).
- **Hol jelenik meg a projektben:** `ASRSettings.language` — "ISO-639-1
  hint, or None for auto-detect" (`app/config.py`).
- **Mit old meg a projektben:** Egységes, szabványos módot ad a nyelv
  megadására az ASR-végpont felé, ahelyett hogy szabad szöveggel
  ("magyar", "Hungarian"...) próbálnánk azt közölni.

### Dot-path (pont-jelöléses útvonal)
- **Általános jelentés:** Egy beágyazott adatstruktúra (pl. JSON) egy
  mélyebb mezőjére mutató jelölés, pontokkal elválasztva a szinteket
  (pl. `result.text` a `{"result": {"text": "..."}}`-ben).
- **Hol jelenik meg a projektben:** `GENERIC_RESPONSE_TEXT_PATH`,
  `GENERIC_RESPONSE_SEGMENTS_PATH` (`app/config.py`).
- **Mit old meg a projektben:** Lehetővé teszi, hogy a `generic`
  ASR-backend konfigurációval (nem kóddal) írja le, hol található a
  szöveg egy tetszőleges struktúrájú JSON-válaszban.

---

## Hogyan függenek össze ezek? — a pipeline egy mondatban

`hangfájl` → **ffmpeg dekódolás** (PCM, 16kHz, mono) → **VAD** (csend
kiszűrése) → **diarizáció** (ki mikor beszélt, anonim `SPEAKER_NN`
szegmensek) → **speaker embedding** minden szegmensre → **koszinusz-
hasonlóság** a regisztrált (**enrollment**) profilokkal (döntés: név szerint
azonosítva vagy anonim marad) → **ASR** (mit mondott) → szabványos, verziózott
**JSON-kontraktus** (vagy **SRT/VTT**) kimenet. Ezt a láncot egy
**config-vezérelt factory**-architektúra fogja össze, **FastAPI/uvicorn**-on
futva, **Docker**-konténerben, **Prometheus**-metrikákkal és **liveness/
readiness probe**-okkal megfigyelve.

---

## 16. Hasznos tanulási sorrend kezdőknek

Ha valaki lineárisan, elejétől a végéig szeretné megérteni a projektet
(nem csak visszakeresésre használja ezt a szójegyzéket), ez egy javasolt
olvasási sorrend a szakaszok közt:

1. **Hangfeldolgozás alapjai** (1. szakasz) — mi is az a hang digitálisan.
2. **VAD → diarizáció → embedding → enrollment → ASR** (2–5. szakasz) —
   a tényleges feldolgozási lánc, lépésről lépésre, pontosan úgy, ahogy a
   README architektúra-diagramja is bemutatja.
3. **API-tervezés** (6. szakasz) — hogyan éri el a külvilág ezt a láncot
   (HTTP/WebSocket végpontok).
4. **Backend-architektúra** (7. szakasz) — *miért* van minden lépés egy
   interfész mögé rejtve, és hogyan cserélhető ki.
5. **Aszinkron programozás + FastAPI/Pydantic** (8–9. szakasz) — *hogyan*
   fut mindez valójában egy Python-szerverben.
6. **Observability, Docker, GPU-üzemeltetés, tesztelés** (10–13. szakasz)
   — hogyan üzemeltethető ez élesben, megbízhatóan.
7. **Egyéb fogalmak** (14. szakasz) — apróbb, de gyakran előkerülő
   kifejezések felszedése.

Ez a sorrend nagyjából megfelel annak, ahogy a README.md is felépíti a
saját magyarázatát: probléma → adatfolyam → végpontok → üzemeltetés.

---

## 17. Ábécérendes gyorskereső

Ha egy konkrét kifejezést keresünk, és nem a tematikus sorrendben
olvasnánk végig a dokumentumot, ez a lista ábécérendben, a megfelelő
szakaszra hivatkozva segít gyorsan megtalálni:

| Kifejezés | Szakasz |
|---|---|
| `.env` fájl | 14. Egyéb fogalmak |
| API-kulcs (API key) | 14. Egyéb fogalmak |
| ASR (Automatic Speech Recognition) | 5. Beszédfelismerés |
| `asyncio.gather` | 8. Aszinkron programozás |
| `asyncio.to_thread` | 8. Aszinkron programozás |
| Aszinkron függvény / `async`/`await` | 8. Aszinkron programozás |
| CI (Continuous Integration) | 13. Tesztelés |
| Config-vezérelt dizájn | 7. Backend-architektúra |
| Konfidencia (confidence score) | 5. Beszédfelismerés |
| Konkurrencia vs. párhuzamosság | 8. Aszinkron programozás |
| Konténer / Docker image | 11. Konténerizáció |
| Koszinusz-hasonlóság | 4. Enrollment |
| Counter / Histogram | 10. Megfigyelhetőség |
| CPU vs. GPU / CUDA | 12. Gépi tanulás |
| Dot-path | 14. Egyéb fogalmak |
| Diarizáció | 3. Beszélő-szétválasztás |
| docker-compose | 11. Konténerizáció |
| ECAPA-TDNN | 4. Enrollment |
| Enrollment | 4. Enrollment |
| Env-változó | 14. Egyéb fogalmak |
| Event loop | 8. Aszinkron programozás |
| FastAPI | 9. Webkeretrendszer |
| Factory (gyár mintázat) | 7. Backend-architektúra |
| ffmpeg / kódolás-dekódolás | 1. Hangfeldolgozás |
| Futó átlag (running average) | 4. Enrollment |
| Gated model | 12. Gépi tanulás |
| Generic backend / mező-map-elés | 5. Beszédfelismerés |
| Healthcheck | 11. Konténerizáció |
| Horizontális skálázás / replika | 11. Konténerizáció |
| HTTP metódusok | 6. API-tervezés |
| HuggingFace | 12. Gépi tanulás |
| Interfész / absztrakt osztály | 7. Backend-architektúra |
| ISO-639-1 | 14. Egyéb fogalmak |
| JSON | 6. API-tervezés |
| Kubernetes (k8s) / rolling deploy | 14. Egyéb fogalmak |
| Laza csatolás (loose coupling) | 7. Backend-architektúra |
| Liveness probe / Readiness probe | 10. Megfigyelhetőség |
| Load balancer | 11. Konténerizáció |
| Mock | 13. Tesztelés |
| Modell-agnosztikus dizájn | 5. Beszédfelismerés |
| Modellsúlyok (model weights) | 12. Gépi tanulás |
| Mono / csatorna | 1. Hangfeldolgozás |
| Multipart/form-data | 6. API-tervezés |
| NFS / EFS | 14. Egyéb fogalmak |
| OOM (Out Of Memory) | 12. Gépi tanulás |
| PCM | 1. Hangfeldolgozás |
| Prometheus / metrika | 10. Megfigyelhetőség |
| Pydantic / `BaseModel` | 9. Webkeretrendszer |
| Pydantic Settings | 9. Webkeretrendszer |
| pyannote.audio | 3. Beszélő-szétválasztás |
| pytest | 13. Tesztelés |
| PyTorch (torch) | 12. Gépi tanulás |
| Query paraméter | 6. API-tervezés |
| Redaktálás | 14. Egyéb fogalmak |
| REST / REST API | 6. API-tervezés |
| Séma-verziózás | 7. Backend-architektúra |
| Silero VAD | 2. VAD |
| Sample rate (mintavételi frekvencia) | 1. Hangfeldolgozás |
| Speaker embedding | 4. Enrollment |
| SRT / WebVTT | 6. API-tervezés |
| Strukturált naplózás | 10. Megfigyelhetőség |
| Többlépcsős build (multi-stage) | 11. Konténerizáció |
| Unit teszt | 13. Tesztelés |
| Uvicorn / ASGI szerver | 9. Webkeretrendszer |
| VAD (Voice Activity Detection) | 2. VAD |
| Volume (kötet) | 11. Konténerizáció |
| WebRTC VAD | 2. VAD |
| WebSocket | 6. API-tervezés |
| WER / CER | 13. Tesztelés |
| Whisper / Whisper API dialektus | 5. Beszédfelismerés |
| YAML konfigurációs fájl | 9. Webkeretrendszer |
readiness probe**-okkal megfigyelve.
