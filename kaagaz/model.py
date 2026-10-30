"""The model boundary. Everything that talks to Meta Model API lives here, behind one method: `extract`.

MuseSpark   - the real client (OpenAI-compatible Chat Completions on https://api.meta.ai/v1, image input, JSON schema output).
ReplayCache - every real call is written to disk as JSON (request fingerprint -> response). The same inputs replay from
              disk without a key, so tests and demos can run on recorded real answers, and so a run can be audited later.
FakeModel   - no network at all: answers from the samples' ground truth. Used by the test-suite and by `--fake`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

DEFAULT_MODEL = "muse-spark-1.3"
DEFAULT_BASE_URL = "https://api.meta.ai/v1"


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    cached: int = 0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds
        self.cached += other.cached


@dataclass
class Reply:
    data: dict
    usage: Usage = field(default_factory=Usage)
    from_cache: bool = False
    raw_text: str = ""


class Model(Protocol):
    name: str

    def extract(self, *, system: str, user_text: str, images: list[bytes], schema: dict, schema_name: str) -> Reply: ...


def fingerprint(*, model: str, system: str, user_text: str, images: list[bytes], schema: dict, schema_name: str,
                temperature: float = 0.0) -> str:
    h = hashlib.sha256()
    h.update(model.encode()); h.update(b"\0")
    h.update(system.encode()); h.update(b"\0")
    h.update(user_text.encode()); h.update(b"\0")
    for img in images:
        h.update(hashlib.sha256(img).digest())
    h.update(schema_name.encode()); h.update(b"\0")
    h.update(f"t={temperature}".encode()); h.update(b"\0")
    h.update(json.dumps(schema, sort_keys=True).encode())
    return h.hexdigest()


class ReplayCache:
    """One JSON file per request fingerprint. Nothing secret is stored: the request text, image hashes, the model's
    answer and token counts."""

    def __init__(self, directory: str | os.PathLike):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        p = self.path(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def put(self, key: str, record: dict) -> None:
        self.path(key).write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    def __len__(self) -> int:
        return len(list(self.dir.glob("*.json")))


def _data_url(image: bytes) -> str:
    mime = "image/png" if image[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(image).decode("ascii")


def _loads_lenient(text: str) -> dict:
    """Parse the model's JSON. A reasoning model may prepend a <think>...</think> block or wrap the answer in
    ```json fences; strip those, then fall back to the outermost {...}."""
    import re
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    t = re.sub(r"```(?:json)?", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j != -1 and j > i:
            return json.loads(t[i:j + 1])
        raise


def load_dotenv_files() -> None:
    """Populate os.environ from .env so KAAGAZ_BASE_URL / KAAGAZ_MODEL / KAAGAZ_STRUCTURED (not just MODEL_API_KEY)
    take effect. Real shell environment variables win over .env. Safe to call repeatedly."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def load_api_key(explicit: Optional[str] = None) -> Optional[str]:
    """Order: explicit argument, MODEL_API_KEY in the environment, a .env file next to the working directory,
    .streamlit/secrets.toml (MODEL_API_KEY = "..."). The key is never printed anywhere."""
    if explicit:
        return explicit
    load_dotenv_files()
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"]
    try:
        from dotenv import dotenv_values
        for candidate in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
            if candidate.exists():
                v = dotenv_values(candidate).get("MODEL_API_KEY")
                if v:
                    return v
    except ImportError:
        pass
    for candidate in (Path(".streamlit/secrets.toml"), Path(__file__).resolve().parent.parent / ".streamlit/secrets.toml"):
        if candidate.exists():
            try:
                import tomllib
                v = tomllib.loads(candidate.read_text(encoding="utf-8")).get("MODEL_API_KEY")
                if v:
                    return v
            except Exception:
                pass
    return None


class MuseSpark:
    """An OpenAI-compatible chat endpoint serving a Muse Spark model: Meta Model API (muse-spark-1.3) or an
    inference partner serving Meta's open-weight Muse Spark Open (Baseten, Fireworks, Modal, self-hosted vLLM).
    Base URL, model id and key come from the environment, so switching provider is a .env change, not a code change.
    One image or several, a system prompt, structured JSON out (strict schema where supported, json_object where not)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None,
                 cache: Optional[ReplayCache] = None, timeout: float = 180.0, replay_only: bool = False):
        load_dotenv_files()
        self.name = model or os.environ.get("KAAGAZ_MODEL", DEFAULT_MODEL)
        self.base_url = base_url or os.environ.get("KAAGAZ_BASE_URL", DEFAULT_BASE_URL)
        self.cache = cache
        self.timeout = timeout
        self.replay_only = replay_only
        # Muse Spark Open is a reasoning model: its hidden reasoning spends output tokens before the JSON, so give a
        # generous ceiling or the structured answer gets truncated. Override with KAAGAZ_MAX_TOKENS.
        self.max_tokens = int(os.environ.get("KAAGAZ_MAX_TOKENS", "16000"))
        # Low temperature on the primary read for a stable, best-effort extraction; a higher one on the second read so
        # it is a genuinely independent sample that can catch (and be caught on) a misread, not a copy of the first.
        self.temperature = float(os.environ.get("KAAGAZ_TEMPERATURE", "0.1"))
        self.audit_temperature = float(os.environ.get("KAAGAZ_AUDIT_TEMPERATURE", "0.45"))
        self._key = None if replay_only else load_api_key(api_key)
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            if not self._key:
                raise RuntimeError("no MODEL_API_KEY: put it in .env (see .env.example) or the environment")
            self._client = OpenAI(base_url=self.base_url, api_key=self._key, timeout=self.timeout, max_retries=2)
        return self._client

    def _create_structured(self, client, messages, schema: dict, schema_name: str, temperature: float = 0.1):
        """Ask for JSON back in the strongest way the endpoint accepts. Meta Model API takes a strict json_schema;
        an open-weight server behind an OpenAI-compatible gateway (Baseten, Fireworks, vLLM) may take json_schema
        without `strict`, or only json_object. We try these in turn and fall back on a 400 only, so a real 401/402/
        rate-limit error still surfaces. KAAGAZ_STRUCTURED can pin one mode: json_schema_strict | json_schema | json_object."""
        from openai import BadRequestError
        forced = os.environ.get("KAAGAZ_STRUCTURED", "auto")
        ladder = []
        if forced in ("auto", "json_schema_strict"):
            ladder.append(("strict", {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}))
        if forced in ("auto", "json_schema"):
            ladder.append(("schema", {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema}}))
        if forced in ("auto", "json_object"):
            aug = list(messages)
            aug[0] = {"role": "system", "content": messages[0]["content"]
                      + "\n\nReturn ONLY one JSON object matching this JSON Schema, no prose and no markdown fences:\n"
                      + json.dumps(schema)}
            ladder.append(("object", {"type": "json_object"}, aug))
        last = None
        for step in ladder:
            mode, rf = step[0], step[1]
            msgs = step[2] if len(step) > 2 else messages
            try:
                return client.chat.completions.create(model=self.name, messages=msgs, response_format=rf, max_tokens=self.max_tokens, temperature=temperature)
            except BadRequestError as e:
                last = e
                continue
        # nothing worked by response_format; one bare attempt so the real error (or the content) surfaces
        if last is not None and forced == "auto":
            aug = list(messages)
            aug[0] = {"role": "system", "content": messages[0]["content"]
                      + "\n\nReturn ONLY one JSON object matching this JSON Schema, no prose and no markdown fences:\n"
                      + json.dumps(schema)}
            return client.chat.completions.create(model=self.name, messages=aug, max_tokens=self.max_tokens, temperature=temperature)
        raise last if last is not None else RuntimeError("no structured-output mode attempted")

    def extract(self, *, system: str, user_text: str, images: list[bytes], schema: dict, schema_name: str) -> Reply:
        temperature = self.audit_temperature if "audit" in schema_name else self.temperature
        key = fingerprint(model=self.name, system=system, user_text=user_text, images=images, schema=schema, schema_name=schema_name, temperature=temperature)
        if self.cache is not None:
            rec = self.cache.get(key)
            if rec is not None:
                u = Usage(calls=0, cached=1, input_tokens=0, output_tokens=0)
                return Reply(data=rec["response"], usage=u, from_cache=True, raw_text=rec.get("raw_text", ""))
        if self.replay_only:
            raise RuntimeError(f"replay-only mode and no cached answer for this request ({key[:12]})")

        client = self._get_client()
        content = [{"type": "text", "text": user_text}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": _data_url(img)}})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        t0 = time.time()
        resp = self._create_structured(client, messages, schema, schema_name, temperature)
        dt = time.time() - t0
        text = resp.choices[0].message.content or ""
        data = _loads_lenient(text)
        usage = Usage(calls=1, seconds=dt,
                      input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
                      output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0)
        if self.cache is not None:
            self.cache.put(key, {
                "model": self.name, "schema_name": schema_name, "system": system, "user_text": user_text,
                "image_sha256": [hashlib.sha256(i).hexdigest() for i in images],
                "response": data, "raw_text": text,
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "seconds": round(dt, 2)},
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        return Reply(data=data, usage=usage, raw_text=text)


class FakeModel:
    """Answers from a dict of image-sha256 -> {schema_name: response}. Anything unknown gets an empty, honest answer.
    `audit_noise` makes the audit read disagree on the listed row numbers, to exercise the dispute path."""

    name = "fake"

    def __init__(self, answers: Optional[dict] = None, audit_noise: Optional[dict] = None):
        self.answers = answers or {}
        self.audit_noise = audit_noise or {}
        self.calls: list[dict] = []

    @classmethod
    def from_samples(cls, samples_dir: str | os.PathLike, audit_noise: Optional[dict] = None) -> "FakeModel":
        from .images import load_pages
        samples_dir = Path(samples_dir)
        answers: dict = {}
        for truth in samples_dir.glob("*.truth.json"):
            rec = json.loads(truth.read_text(encoding="utf-8"))
            for image_name in rec.get("images", []):
                p = samples_dir / image_name
                if p.exists():
                    # keyed by the model-ready bytes (what the pipeline actually sends), not the file on disk
                    for page_bytes in load_pages(p):
                        answers[hashlib.sha256(page_bytes).hexdigest()] = rec
        return cls(answers, audit_noise)

    def extract(self, *, system: str, user_text: str, images: list[bytes], schema: dict, schema_name: str) -> Reply:
        self.calls.append({"schema_name": schema_name, "n_images": len(images)})
        rec = None
        for img in images:
            rec = self.answers.get(hashlib.sha256(img).hexdigest())
            if rec:
                break
        if rec is None:
            if schema_name == "order_read":
                data = {"court": "", "case_reference": "", "order_date": "", "charges": [], "custody_start": "",
                        "first_time_offender": "unknown", "other_cases_pending": "unknown", "section_479_invoked": False,
                        "decision": "other", "decision_quote": "", "period_served_quote": ""}
            else:
                data = {"page_kind": "other", "language": "", "period_or_date": "", "rows": []}
            return Reply(data=data, usage=Usage(calls=1))
        if schema_name == "order_read":
            data = json.loads(json.dumps(rec["order_read"]))
        elif schema_name.startswith("page_read"):
            data = json.loads(json.dumps(rec["page_read"]))
            if "audit" in schema_name and self.audit_noise:
                for row in data["rows"]:                       # the second read disagrees on the listed rows
                    noise = self.audit_noise.get(row["row_no"])
                    if noise:
                        row.update(noise)
        else:
            raise ValueError(schema_name)
        return Reply(data=data, usage=Usage(calls=1))
