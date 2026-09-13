# Útmutató — hangprofil-regisztrációs (enrollment) felvételek készítése

Ez a mappa a `POST /v1/speakers` végponthoz (`app/api/speakers.py`)
készített, **felmondásra szánt szövegeket** tartalmazza — magyarul és
angolul külön —, valamint ezt az útmutatót, hogy a felvett hanganyag
minél jobb minőségű hangprofilt ("voiceprint") eredményezzen.

- [`enrollment_text_hu.md`](enrollment_text_hu.md) — magyar szöveg
- [`enrollment_text_en.md`](enrollment_text_en.md) — angol szöveg
  ("The Rainbow Passage")

## Miért van külön magyar és külön angol szöveg?

A pipeline-ban (ld. [`../terminologia.md`](../terminologia.md)) két,
egymástól **függetlenül cserélhető** modell-típus dolgozik a hangon:

- Az **ASR-backend** (`ASR_BACKEND`, `ASR_MODEL`) — ez alakítja szöveggé
  a beszédet, és jellemzően **nyelv-specifikus** (egy magyarra
  finomhangolt Whisper-modell jobban teljesít magyar beszéden, egy
  angolra finomhangolt jobban angolon).
- A **beszélő-embedding backend** (`EMBEDDING_BACKEND` —
  `pyannote_embedding` / `speechbrain_ecapa`) — ez csak azt méri, *hogyan
  szól* a hangod (hangszín, formánsok, prozódia), nem azt, *milyen
  nyelven* beszélsz. Ezek a modellek nagy, sokféle nyelvet tartalmazó
  adathalmazon (pl. VoxCeleb) lettek tanítva, ezért a hangprofil-egyezés
  (`app/core/enrollment/matcher.py`, koszinusz-hasonlóság) nagyrészt
  nyelv-független.

Ennek ellenére két okból éri meg a saját anyanyelveden (is) felvenni az
enrollment-mintát:

1. **Természetesebb prozódia** — a saját anyanyelveden a hanglejtésed,
   tempód és hangsúlyaid a legtermészetesebbek; egy idegen nyelven
   felolvasott, esetleg akadozó felmondás kevésbé jellemző mintát ad a
   hangodról, mint amilyen a valódi (pl. magyar nyelvű) megbeszéléseken
   hallható lesz.
2. **Ha a projekt mindkét ASR-nyelvet kiszolgálja** — a README szerint a
   worker modell-agnosztikus, tehát elképzelhető, hogy egy telepítés
   magyar megbeszéléseken magyarra hangolt, míg máskor/más csapatnál
   angolra hangolt ASR-t hív. Ha mindkét nyelven van enrollment-mintád
   (két külön `name`/profil, vagy egy profilba felváltva feltöltve —
   mindkettő működik, mert a futó átlag csak a hangszínt kevergeti, nem
   a nyelvet), a hangprofilod ugyanolyan jól felismerhető marad,
   függetlenül attól, melyik nyelven zajlik éppen a megbeszélés.

Ha csak egy nyelven használod a rendszert, elég csak azon a nyelven
felvenni a mintát — a másik szöveg csak akkor releváns, ha tényleg
szükséged van rá.

## Hány felvétel, milyen hosszú?

Röviden összefoglalva (részletesebben ld. a beszélgetés korábbi részét):

- **Összesen kb. 2–3 perc**, **2–3 külön, egyenként kb. 45–75 másodperces
  felvételre** bontva — ne egyetlen hosszú, egybefüggő felvételt tölts
  fel.
- Minden részt **külön `POST /v1/speakers` hívással** tölts fel,
  **ugyanazzal a `name` értékkel** — az enrollment-tároló
  (`app/core/enrollment/store.py`, `upsert`) ismételt regisztrációnál
  **futó átlagot** számol a korábbi és az új hangvektor között, nem
  felülírja azt. Több, kissé eltérő tempójú/hangulatú minta ezért
  robusztusabb, stabilabb profilt ad, mint egy hosszú, monoton felolvasás.
- Ideális esetben a 2–3 felvétel **ne egy ülésben, egymás után**
  készüljön, hanem — ha ráérsz — kicsit eltérő időpontokban/hangulatban
  (pl. reggel és este), hogy a profil a hangod természetes napi
  ingadozását is lefedje.

## Mire figyelj felvétel közben — tartalom és stílus

- **Beszélj természetesen**, a szokásos napi hangerőddel és tempóddal.
  Ne olvass fel robotikusan, szótagolva, se túl lassan, se hadarva — a
  cél az, hogy a modell a *valódi*, mindennapi hangodat lássa, nem egy
  "felmondás-hangot".
- **Egy ülésben, megszakítás nélkül** olvasd fel az adott részt. Ha
  elrontod, inkább kezdd újra az egész szakaszt, mint hogy egy vágott,
  összeillesztett felvételt adj be — a vágási pontok hallható
  akadásokat/csendeket hagyhatnak a hangban.
- **Váltogasd a hangnemet** — a három magyar/angol szövegrész szándékosan
  más-más stílusú (nyugodt elbeszélés, kérdések, meglepett felkiáltás),
  mert ez jobban lefedi a hangod természetes hangszín-tartományát, mint
  ha mindig ugyanazt a semleges "hírolvasó hangot" használnád.
- **Ne suttogj és ne kiabálj** — a normál beszélgetési hangerő adja a
  legjobb, a valós használati esethez (megbeszélés) leginkább hasonló
  mintát.

## Mire figyelj technikailag — miért fontos ez ennél a projektnél

A `POST /v1/speakers` végpont az enrollment-felvételt **egészben, VAD
(csendszűrés) nélkül** adja át az embedding-modellnek (`app/core/
embedding.py`, `window="whole"` — a teljes klip egyetlen vektorrá
alakul). Ez a batch/streaming leiratozási pipeline-tól eltérő eljárás
(ott előbb VAD/diarizáció szűri a csendet), ezért enrollmentnél **rád**
van bízva, hogy a felvétel jó minőségű legyen:

- **Vágd le a hosszú csendeket a felvétel elején és végén** (max. kb.
  fél másodpercnyi maradjon) — a beépített csendrészek felhígítják az
  embedding-vektort, és rontják a későbbi koszinusz-hasonlóság alapú
  egyezést (`EMBEDDING_SIMILARITY_THRESHOLD`, alapérték `0.75`).
- **Csendes helyiségben rögzíts** — kerüld a visszhangos termeket
  (üres, nagy, csempézett/kőpadlós helyiség), a háttérzajt (klíma,
  ventilátor, utcazaj, másik beszélő), és lehetőleg ne a mikrofon
  automatikus zajszűrésére/AGC-jére hagyd a tisztítást — egy csendes
  helyiségben natúr felvétel jobb, mint egy zajos helyen erősen
  utófeldolgozott.
- **Tartsd állandó távolságban a mikrofont** a szádtól (kb. 15–20 cm,
  ha külön mikrofont/headsetet használsz) — a hirtelen távolság-változás
  hangerő-ingadozást okoz a felvételen belül.
- **Formátum:** bármilyen, a projekt által elfogadott formátum jó
  (a worker `ffmpeg`-gel dekódol, ld. [`../terminologia.md`](../terminologia.md)
  "ffmpeg" szócikke) — törekedj tömörítés nélküli vagy alacsony
  tömörítésű forrásra (WAV/FLAC, vagy legalább jó bitráте-ű MP3/M4A), ne
  egy erősen tömörített, telefonos hívásból exportált, recsegő
  hanganyagra.
- **Mono felvétel is elég** — a pipeline mindenképp mono, 16 kHz-re
  konvertál mindent, tehát nem kell sztereóban vagy magas mintavételi
  frekvencián rögzíteni; a lényeg a tiszta, torzításmentes hangforrás.

## Ellenőrző lista feltöltés előtt

- [ ] A felvétel csendes helyiségben készült, hallható háttérzaj nélkül.
- [ ] A felvétel elején/végén nincs több fél másodperces csendnél.
- [ ] Egy megszakítás nélküli, természetes tempójú felolvasás (nem vágott
      össze több próbálkozásból).
- [ ] Normál beszélgetési hangerő, nem suttogott vagy kiabált.
- [ ] A 2–3 részt külön fájlként, külön `POST /v1/speakers` hívással,
      ugyanazzal a `name` értékkel töltötted fel.

## Források

- [The Rainbow Passage (Fairbanks, 1960) — UCLA Phonetics Lab](https://www.phonetics.ucla.edu/voiceproject/English_Rainbow/English_Rainbow_Text.pdf) —
  a `enrollment_text_en.md`-ben használt, fonetikailag kiegyensúlyozott,
  közkincs angol szöveg forrása; a beszélő-verifikáció/enrollment
  szakirodalomban elterjedten használt referencia-szöveg.
- [IDEA: International Dialects of English Archive — The Rainbow Passage](https://www.dialectsarchive.com/the-rainbow-passage) —
  a szöveg egy további, nyilvánosan elérhető közlése.
- [Harvard Sentences — Wikipedia](https://en.wikipedia.org/wiki/Harvard_sentences) —
  háttérinfó: a beszélő-verifikációs kutatásban a Rainbow Passage-t
  jellemzően *enrollment*-re, a Harvard Sentences-t pedig *tesztelésre*
  használják külön-külön.
- Magyar nyelven **nem** létezik ehhez hasonló, egyetlen, széles körben
  elfogadott, szabadon felmondható enrollment-referenciaszöveg (a hazai
  kutatási korpuszok, pl. [BEA](https://fonetika.nytud.hu/bea-beszelt-nyelvi-adatbazis/?lang=en)
  és MTBA, saját, nem erre a célra szánt mondatlistákkal dolgoznak) —
  ezért az [`enrollment_text_hu.md`](enrollment_text_hu.md) tartalma
  saját összeállítás, a fenti elvek (hangkészlet-változatosság,
  természetes hanglejtés-változatosság) alapján.
