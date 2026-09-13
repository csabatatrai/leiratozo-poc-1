# English enrollment text — "The Rainbow Passage"

Use this text for enrolling an English-speaking voice profile
(`POST /v1/speakers` with `audio` recorded while reading it aloud).

## Why this text

"The Rainbow Passage" (Fairbanks, 1960) is a public-domain, **phonetically
balanced** paragraph — it deliberately covers the full range of English
vowel and consonant sounds at roughly their natural frequency of occurrence.
It is a long-standing standard in speech science and is explicitly used in
voice-data collection for **speaker verification/enrollment** (typically
paired with the Harvard Sentences for *testing*, while the Rainbow Passage
itself is read for *enrollment*). That makes it a good default here too:
reading it naturally exposes the embedding model to a wide, representative
sample of your voice, rather than to a narrow, repetitive set of sounds.

Source: [The Rainbow Passage — UCLA Phonetics Lab](https://www.phonetics.ucla.edu/voiceproject/English_Rainbow/English_Rainbow_Text.pdf),
also reproduced by [IDEA: International Dialects of English Archive](https://www.dialectsarchive.com/the-rainbow-passage)
and [University of York](https://www.york.ac.uk/media/languageandlinguistics/documents/currentstudents/linguisticsresources/Standardised-reading.pdf).

## How to use it for this project

Read it in **2–3 separate takes**, each roughly 45–75 seconds, and upload
each take as its own `POST /v1/speakers` call with the same `name` — the
enrollment store averages repeated samples into one profile
(`app/core/enrollment/store.py`), so several natural, independent takes
build a more robust voiceprint than one long, single reading. See
`../voiceprint/README.md` for full recording guidance.

---

## Take 1 (~60–75 seconds)

> When the sunlight strikes raindrops in the air, they act as a prism and
> form a rainbow. The rainbow is a division of white light into many
> beautiful colors. These take the shape of a long round arch, with its
> path high above, and its two ends apparently beyond the horizon.
>
> There is, according to legend, a boiling pot of gold at one end. People
> look, but no one ever finds it. When a man looks for something beyond
> his reach, his friends say he is looking for the pot of gold at the end
> of the rainbow.

## Take 2 (~45–60 seconds)

> Throughout the centuries people have explained the rainbow in various
> ways. Some have accepted it as a miracle without physical explanation.
> To the Hebrews it was a token that there would be no more universal
> floods. The Greeks used to imagine that it was a sign from the gods to
> foretell war or heavy rain.
>
> The Norsemen considered the rainbow as a bridge over which the gods
> passed from earth to their home.

## Take 3 (~45–60 seconds)

> Aristotle thought the rainbow was caused by reflection of the sun's rays
> by the rain. Since then physicists have found that it is not reflection,
> but refraction by the raindrops which causes the rainbows.
>
> Many complicated ideas about the rainbow have been formed. The
> difference in the rainbow depends considerably upon the size of the
> drops, and the width of the colored band increases as the size of the
> drops increases. If the red of the second bow falls upon the green of
> the first, the result is to give a bow with an abnormally wide yellow
> band, since red and green light when mixed form yellow.

---

## Optional: more material if you want extra takes

If you want a fourth or fifth take for an even more robust profile, two
other well-known, public-domain, phonetically diverse English passages
used in speech research are:

- **"Comma Gets a Cure"** — a modernized, phonetically balanced passage
  designed as an updated alternative to the Rainbow Passage, widely used
  in accent/voice research. Commonly available through university speech
  and hearing science course pages.
- **The "Grandfather Passage"** — another classic phonetically balanced
  passage used in speech-language pathology assessment.

Either works the same way: read it naturally, in one continuous take, and
upload it as one more enrollment sample.
