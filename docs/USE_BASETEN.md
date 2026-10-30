# Running Kaagaz on Muse Spark Open via Baseten

Meta's **Muse Spark Open** is Meta's open-weight model. The hackathon rules accept a project that "reasonably used
Meta Model API **and/or Meta's open-weight models**", so this path qualifies fully — and it makes the entry eligible
for the $10,000 "Best Build on Meta Open Weight Models" bonus. It also avoids the Meta Model API card-hold step.

## 1. Get a Baseten key

1. Sign up at https://app.baseten.co (new accounts get $30 in free credit — enough for hundreds of page reads).
2. In the dashboard: **API keys → Create new API key**, copy it.
3. (Optional, for more headroom) Request the hackathon's $100 Baseten credits via the link in the participant guide.

## 2. Point Kaagaz at Baseten

Edit `C:\Users\TTPL-LNV-0319\Downloads\kaagaz\.env` so it reads exactly:

```
MODEL_API_KEY=<your baseten key>
KAAGAZ_BASE_URL=https://inference.baseten.co/v1
KAAGAZ_MODEL=meta-models/muse-spark-open
```

(No spaces around `=`, no quotes.)

## 3. Check and run

```bat
python -m kaagaz.cli check
```

`check` now does a real one-token generation, so a success here means the account can actually run (not just that the
key is valid). Expect `READY - model replied: 'ok'`.

Then:

```bat
python -m kaagaz.cli read samples\register_en_clean.png --as-of 2026-10-31 --out out\en.csv
```

## Notes

* Kaagaz asks for structured JSON the strongest way the endpoint supports (strict schema, then plain schema, then
  json_object), so it works across providers. If Muse Spark Open returns malformed JSON, pin `KAAGAZ_STRUCTURED=json_object`
  in `.env` and re-run.
* Vision: Muse Spark Open takes image input; Kaagaz sends each page as a data URL in the standard OpenAI content format.
* To switch back to Meta Model API later, comment out the two `KAAGAZ_` lines and set `KAAGAZ_MODEL=muse-spark-1.3`.
* Fireworks and Modal also serve Muse Spark Open; set `KAAGAZ_BASE_URL`/`KAAGAZ_MODEL` to their values the same way.
