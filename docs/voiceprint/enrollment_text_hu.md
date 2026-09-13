# Magyar felmondandó szöveg — hangprofil-regisztrációhoz

Ezt a szöveget használd magyar nyelvű hangprofil regisztrálásához
(`POST /v1/speakers`, `audio` mezőben a felmondás felvételével).

## Miért ez a szöveg

Az angol nyelvterületen létezik egy bevett, nyilvánosan elérhető,
fonetikailag kiegyensúlyozott szöveg pont erre a célra (a "Rainbow
Passage" — ld. [`enrollment_text_en.md`](enrollment_text_en.md)), de
ehhez **nincs** egyetlen, széles körben elfogadott, szabadon felmondható
magyar megfelelő, amit hangprofil-regisztrációhoz szánnának (a kutatásban
ismert magyar korpuszok — pl. BEA, MTBA — saját, nem szabadon
felmondható mondatlistákat használnak). Ezért ez a három szövegrész saját
összeállítás, azzal a céllal, hogy egy rövid, természetes felolvasás
közben a lehető legtöbb magyar hangot (magánhangzókat, köztük az á, é, í,
ó, ő, ú, ű, ö, ü hosszú/rövid párjait, és jellegzetes mássalhangzókat,
mint a **sz, zs, cs, gy, ny, ty**) és mondattípust (kijelentő, kérdő,
felkiáltó) lefedjen.

> A `ly` hangot a mai köznyelvi magyar kiejtés már nem különbözteti meg a
> `j`-től — ezért ez nincs külön "kikényszerítve" a szövegekben, hallásra
> ugyanúgy szólna, mint egy `j`.

## Hogyan használd a projektben

Mondd fel a három részt **külön felvételként**, egyenként kb. 45–75
másodpercben, és mindegyiket külön `POST /v1/speakers` hívással töltsd
fel, **ugyanazzal a `name` értékkel**. Az enrollment-tároló (`app/core/
enrollment/store.py`) ismételt regisztrációnál futó átlagot számol, nem
felülír — így a három, kissé eltérő hangulatú/tempójú felvétel egy
robusztusabb hangprofilt ad össze, mint egyetlen hosszú felolvasás.
Részletes felvételi tanácsokért ld. a mappa [`README.md`](README.md)
fájlját.

---

## 1. rész — nyugodt, elbeszélő hangnem (~45–60 másodperc)

> Szombat reggel volt, amikor kinyitottam az ablakot, és a friss, hűvös
> levegő betöltötte a szobát. A kertben egy öreg fűzfa állt, ágai lassan
> ringtak a szélben. Először egy csésze kávét főztem magamnak, majd
> leültem a teraszra, és hallgattam, hogyan zizegnek a levelek. Kilenc óra
> körül elindultam a piacra, ahol friss zsemlét, sajtot és néhány
> gyönyörű, érett almát vásároltam. Hazafelé betértem a könyvesboltba is,
> mert régóta kerestem egy jó receptkönyvet a nagymamám tükörtojásos
> reggelijéhez. Az idő gyorsan járt, mire hazaértem, dél is elmúlt már.

## 2. rész — élénk, kérdésekkel teli hangnem (~45–60 másodperc)

> Szia! Hány órakor érünk oda pontosan? Az anyám azt mondta, fél
> tizenkettőre kellene ott lennünk, de szerintem simán ráérünk egy órával
> később is. Emlékszel még arra a kis cukrászdára a főtéren, ahol azt a
> csodálatos csokis tortát ettük? Kíváncsi vagyok, vajon most is olyan
> finom fagylaltjuk van, mint tavaly nyáron. Egyébként vittél magaddal
> esőkabátot? Mert az égen már gyülekeznek a felhők, és nem szeretnék
> bőrig ázni séta közben. Ja, és ne feledd el a szemüvegedet se, mert
> legutóbb kénytelen voltam kölcsönadni a magamét!

## 3. rész — meglepett, felkiáltó hangnem (~45–60 másodperc)

> Nahát, ezt nem hiszem el! Képzeld, amikor kiléptem a házból, ott állt
> egy hattyú a kerti tóban, pontosan a rózsaszín rózsák mellett! Annyira
> meglepődtem, hogy majdnem elejtettem a bögrémet. A macskánk azonnal
> odaszaladt, de a hattyú egy füttyentésre elrepült a szomszéd zsúfolt
> kertjébe. Utána még egy vadmalac is átfutott az udvaron, egyenesen a
> tűzhely mellett álló fűzfa alá! Micsoda egy reggel volt ez, mondhatom!
> Este majd mindenkinek elmesélem, hogy mi történt itt, ezen a
> nyugalmasnak hitt vasárnap délelőttön.

---

## Opcionális: ha egy negyedik/ötödik felvételt is szeretnél

Ha még robusztusabb profilt akarsz, mondj fel egy rövid, szabadon
kitalált, kb. 1 perces történetet a saját szavaiddal — pl. mesélj el egy
tegnapi eseményt, vagy írj le egy kedvenc receptet. A lényeg, hogy
**természetesen**, a saját, mindennapi hanglejtéseddel beszélj, ne a
fenti szövegek ismétlésével.
