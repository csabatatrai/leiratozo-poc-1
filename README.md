# meeting-speaker-adaptation — beszélőre rátanított Whisper-diarizáció (placeholder)

Állapot: **terv, nem indult el, csak placeholder mappa/dokumentum**.
Létrehozva: 2026-09-10, a `rocketchat-agentic-poc/docs/plans/not-started/
repo_szetvalasztas_terv.md` 5. szakaszában már felvázolt "Whisper-alapú
beszélő-adaptációs projekt (jövőbeli, névtelen)" konkretizálásaként. Ez a
mappa MA csak a helyet foglalja a térképen — nincs benne kód, nincs `.git`
(azt majd a felhasználó inicializálja saját termináljából, ha a projekt
tényleg elindul).

## Miért kell ez — a mai megoldás korlátja

A `meeting-recorder` + a generikus Whisper-végpont ma **csatorna/account
szerint** különbözteti meg a beszélőket: minden résztvevő a saját Jitsi-
hangsávján érkezik, tehát a "ki mondta" kérdés eleve adott, diarizáció
nélkül (ld. `rocketchat-agentic-poc/docs/plans/in-progress/
meeting_leirat_pipeline_terv.md` §10 — a Jitsi SFU-ból résztvevőnkénti
hangkinyerés).

Ez a projekt egy **nehezebb, más esetre** készül: **egy account, egy
mikrofon, TÖBB beszélővel keverve** (pl. valaki felhív egy megbeszélést a
saját telefonjáról/laptopjáról, de a szobában többen ülnek egy mikrofon
körül). Itt nincs résztvevőnkénti sáv — a szétválasztást a hangból magából
kell kinyerni, és a cél, hogy ez a szétválasztás a beszélőkre "rátanítva"
(enrollment) pontosabb legyen, mint egy generikus, névtelen diarizáció.

## Javasolt belső pipeline

```
nyers hang (1 csatorna, N beszélő, keverve)
      │
      ▼
1) VAD (hang-aktivitás detektálás) — beszédszegmensek kivágása csendből
      │
      ▼
2) Diarizáció (pl. pyannote.audio) — anonim klaszterezés:
   "Beszélő A / B / C" + szegmens-időbélyegek
      │
      ▼
3) Beszélő-embedding kinyerés szegmensenként
   (pl. SpeechBrain ECAPA-TDNN, vagy a diarizációs könyvtár saját
   embedding-modellje)
      │
      ▼
4) Enrollment-egyeztetés — koszinusz-hasonlóság az előre felvett
   "kollégák hangprofiljai" ellen. Elég közeli match → ismert névre
   fordítva; nincs elég közeli match → marad "Beszélő N" (anonim)
      │
      ▼
5) ASR (whisper-large-v3-hu, helyben vagy a meglévő GPU-végponton)
   szegmensenként
      │
      ▼
6) Időrendi összefésülés → beszélő-címkézett leirat-JSON kimenet
```

**Enrollment-mechanizmus**: a kollégák felmondanak egy pár perces szöveget
egyszer; ebből egy vagy több embedding-vektor kerül eltárolásra, mint saját
"hangprofil". Egy maroknyi kollégához ehhez nem kell full vektor-adatbázis
— egy egyszerű, lokális JSON/pickle-store is elég (kulcs: név, érték:
átlagolt embedding-vektor(ok)).

## Külső szerződés — a laza csatolás elve

A komponens kifelé **kizárólag** ezt tudja: `hangfájl-be → beszélő-
címkézett leirat-JSON-ki` (élő módban: `hang-chunk-be → időrendi részleges
leirat-ki`). **Nulla ismeret** arról, honnan jött a hang (Jitsi, telefon,
más), és **nulla ismeret** Rocket.Chat-ről, Hermesről, OpenClaw-ról vagy
bármelyik connectorról — pontosan ugyanaz az elv, mint a
`services/whisper-transcribe` vagy a `meeting-recorder` esetében.

Amikor ez a komponens elkészül, a `meeting-recorder` egy **opcionális,
új whisper-backendként** hívhatná meg (a mai `WHISPER_ENDPOINT_URL`/
`WHISPER_ENDPOINT_MODEL` env-minta mentén, ld. `meeting-recorder/README.md`
"Konfiguráció" szakasza), amikor multi-speaker-egy-csatorna esetet észlel.

## Jitsi mint demo-UI — fontos elhatárolás

**A Jitsi NEM ennek a projektnek a függősége.** Demózáshoz a meglévő
`rocketchat-agentic-poc`/`meeting-recorder` oldali Jitsi-infrastruktúra
(`scripts/testing/fake-meeting/` Playwright-alapú szimulált résztvevők)
adná az "élő hangbemenetet" — ezt a `meeting-recorder` már ma is ki tudja
nyerni és tovább tudja adni egy hang-végpontnak. Ez a komponens kódja
ettől teljesen független marad: csak hangfájlt/hangchunkot fogad, sosem
tartalmaz Jitsi-specifikus (WebRTC/`lib-jitsi-meet`) kódot. Ha holnap más
lenne a hívás-app (pl. Mattermost Calls, Matrix/Element Call), ennek a
projektnek a kódjában semmi nem változna.

## Teszt-adat-stratégia — `meeting-audio-forge` kettős felhasználása

A `meeting-audio-forge` kimenete (ld. saját `README.md`-je) két célra is
kiválóan használható, kódimport nélkül, tisztán fájlrendszeri kimenet-
fogyasztásként (a `meeting-recorder/fixture-audio.mjs`
`MEETING_AUDIO_FORGE_ROOT`-mintáját követve):

- **`meeting.wav` + `ground_truth.json`** (`speakers[]`, `turns[].
  {speaker,text,start,end}` séma) — ez maga a célzott eset: egy
  összekevert, több-beszélős fájl. Egyben ez a kiértékelési alap is —
  WER/CER **és** beszélő-attribúciós pontosság mérhető ellene, a
  `meeting-recorder/evaluate_transcript.py` mintájára kiterjesztve.
- **`{Beszélő}.wav`** (per-beszélő tiszta felvételek) — tökéletes
  "enrollment"-teszt-adat valódi kollégák bevonása nélkül: minden
  szintetikus beszélőhöz van tiszta referenciahang, amivel a 4. lépés
  (enrollment-egyeztetés) önmagában, korán tesztelhető.

## Nyitott döntések (még nincs eldöntve, csak felsorolva)

- Diarizációs könyvtár választása (pl. `pyannote.audio` vagy alternatíva).
- Beszélő-embedding modell választása.
- Hol fusson: a fejlesztői gépnek nincs AVX2-je/CUDA-ja (ld.
  `meeting_leirat_pipeline_terv.md` §5 hardver-korlátai) — ez itt is
  releváns lehet, tehát GPU-hozzáférés (a meglévő Kristóf-féle végpont
  mintájára) valószínűleg itt is szükséges lesz.
- Élő streaming vs. batch-feldolgozás — melyikkel induljon az MVP.
- Az enrollment-store konkrét formátuma/technológiája (fájl-alapú elég,
  vagy kelljen valódi vektor-DB).

## Explicit NEM-cél most

- Bármilyen Rocket.Chat/Hermes/OpenClaw/chat-platform-ismeret.
- UI-réteg építése — ez bármelyik fogyasztó (pl. `meeting-recorder`) dolga.
- Éles bevezetés — ez egy kutatás-fejlesztési fázisú, kísérletezős projekt,
  saját tempóban, GPU-igényes tréninggel/kísérletezéssel.
