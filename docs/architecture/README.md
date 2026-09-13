# Architektúra-diagramok (szabványos UML jelöléssel, Mermaid kóddal)

Három diagram, mindegyik egy-egy más UML nézetet ad a workerről — mindhármat
valós `mermaid-cli`-vel (v11) lerenderelve ellenőriztük hibamentesnek, mielőtt
ide kerültek:

1. [`sequence_diagram.md`](sequence_diagram.md) — **Sequence Diagram**: a
   batch és élő kérés-válasz lefutása, aktivációs sávokkal (`+`/`-`
   jelöléssel minden szinkron hívásnál).
2. [`component_diagram.md`](component_diagram.md) — **Class Diagram**
   `<<interface>>` stereotype-okkal és realizációs/függőségi nyilakkal, a
   valódi UML Component Diagram legpontosabb Mermaid-megfelelője: a
   pluggable-backend architektúrát (interfész vs. konkrét implementáció)
   mutatja.
3. [`state_diagram.md`](state_diagram.md) — **State Machine Diagram**: az
   élő `StreamingSession` puffer-gyűjtés → lezárás → esemény-kiadás
   állapotgépe.

Ugyanezek közül a szekvenciadiagram a fő [`README.md`](../../README.md)-ben
is szerepel (ott a projekt kötelező 3 ábrájának egyike); a Class és State
diagram itt, a `docs/architecture/` mappában önállóan, kifejezetten UML-
szabványos jelöléssel készült el, kiegészítve a README-ben lévő,
kevésbé formális flowchart-ábrákat.
