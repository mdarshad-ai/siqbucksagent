"""
GemGenerate: AI previews of a stone set in jewellery ("how would it look in
a ring?").

Siq and Bucks call it as a tool. The stone's real catalogue photo goes to a
cheap image model on OpenRouter as a reference, with a fixed prompt built
here from the stone's details - the partners never write image prompts
themselves. Each preview is saved to storage and reused for the same
request, so repeats are free.
"""

import base64
import hashlib
import logging
import os
import re
import uuid

import httpx

import database
import limits
import llm_service
from storage import IMAGE_TYPES, get_storage

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_MODEL = "google/gemini-3.1-flash-lite-image"
# Offered in the admin tester; any OpenRouter model that takes an image in
# and gives an image out works.
MODEL_CHOICES = [
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "qwen/qwen-image-3",
    "bytedance-seed/seedream-5-0-lite",
    "black-forest-labs/flux.2-klein-4b",
]
_MODEL_ID = re.compile(r"^[a-z0-9._-]+/[a-z0-9._:-]+$", re.I)

SETTINGS = {
    "ring": ("ring", "a ring, shown at a slight angle so both the stone and the band are visible"),
    "pendant": ("pendant", "a pendant on a fine chain"),
    "earrings": ("earring", "a drop earring (show a single earring)"),
    "bracelet": ("bracelet", "a bracelet, with this stone as the centrepiece"),
}
METALS = {
    "yellow_gold": "yellow gold",
    "white_gold": "white gold",
    "rose_gold": "rose gold",
    "platinum": "platinum",
}
STYLES = {
    "solitaire": "a classic solitaire setting",
    "halo": "a halo of small white diamonds around the stone",
    "vintage": "a vintage, finely engraved setting",
    "minimal": "a sleek, minimal modern setting",
}

MAX_REFERENCE_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT_SECONDS = 75
PROMPT_VERSION = "1"  # bump to regenerate every saved preview


class GemGenerateError(Exception):
    """Something the partner should hear about in plain words."""


# ---------- model choice ----------

def current_model() -> str:
    stored = database.get_settings_rows().get("image_model")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return os.environ.get("IMAGE_MODEL", "").strip() or DEFAULT_IMAGE_MODEL


def valid_model(model: str) -> bool:
    return bool(_MODEL_ID.match(model or ""))


def set_model(model: str, user_email: str):
    database.set_settings({"image_model": model}, user_email)


# ---------- building the request ----------

def describe(setting: str, metal: str, style: str = "") -> str:
    """A short label for the preview, e.g. "Halo ring in white gold"."""
    noun = SETTINGS[setting][0] if setting != "earrings" else "earrings"
    words = f"{style} {noun}" if style else noun
    return f"{words[0].upper()}{words[1:]} in {METALS[metal]}"


def build_prompt(item: dict, setting: str, metal: str, style: str = "") -> str:
    details = ", ".join(
        str(v) for v in (
            f"{item['carat']} ct" if item.get("carat") else None,
            item.get("cut"),
            item.get("color"),
            item.get("category"),
        ) if v
    )
    style_text = STYLES.get(style, "a setting that suits the stone")
    return (
        "Create a photorealistic jewellery product photo. The attached photo "
        f"shows a loose gemstone ({details or item['name']}). Set this exact "
        f"stone in {SETTINGS[setting][1]}, made of polished {METALS[metal]}, "
        f"with {style_text}. Keep the stone's colour, cut, shape and "
        "character exactly as in the photo, sized realistically for "
        f"{'its carat weight' if item.get('carat') else 'the piece'}. "
        "Studio lighting, soft neutral background, sharp focus on the stone. "
        "No people, no hands, no text, no logos, no watermark."
    )


def cache_key(photo: dict, setting: str, metal: str, style: str, model: str) -> str:
    raw = f"{photo['id']}|{photo['path']}|{setting}|{metal}|{style}|{model}|{PROMPT_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


def reference_photo(item: dict):
    """The stone's catalogue photo (the chosen one, else its first photo)."""
    return database.first_images([item["id"]]).get(item["id"])


def _data_url(photo: dict) -> str:
    data = get_storage().read(photo["path"])
    if len(data) > MAX_REFERENCE_BYTES:
        raise GemGenerateError("the stone's photo is too large to use as a reference")
    content_type = photo.get("content_type") or "image/jpeg"
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


# ---------- calling the image model ----------

_DATA_URL = re.compile(r"^data:(image/[a-z+.-]+);base64,(.+)$", re.I | re.S)


def _decode_image(url: str):
    """(bytes, content_type) from a data URL or a plain image link."""
    match = _DATA_URL.match(url or "")
    if match:
        return base64.b64decode(match.group(2)), match.group(1).lower()
    if url and url.startswith("https://"):
        res = httpx.get(url, timeout=60)
        res.raise_for_status()
        return res.content, res.headers.get("content-type", "").split(";")[0].lower()
    raise GemGenerateError("the image model didn't return an image")


def _first_image(message: dict):
    for image in message.get("images") or []:
        url = (image.get("image_url") or {}).get("url") if isinstance(image, dict) else None
        if url:
            return url
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return (part.get("image_url") or {}).get("url")
    return None


def call_image_model(prompt: str, reference_url: str, model: str):
    """Ask the image model for one picture. Returns (bytes, content_type)."""
    # Gemini answers with text and an image; image-only models want just "image".
    modalities = ["image", "text"] if "gemini" in model else ["image"]
    extra = {"modalities": modalities}
    if "gemini" in model:
        extra["image_config"] = {"aspect_ratio": "1:1"}
    # No retries, and well under Cloudflare's 100 s idle limit: the chat
    # stream is silent while the picture is made.
    client = llm_service._get_client().with_options(timeout=IMAGE_TIMEOUT_SECONDS, max_retries=0)
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": reference_url}},
            ],
        }],
        extra_body=extra,
        extra_headers=llm_service._extra_headers(),
    )
    if not response.choices:
        raise GemGenerateError("the image model didn't return an image")
    data, content_type = _decode_image(_first_image(response.choices[0].message.model_dump()))
    if content_type not in IMAGE_TYPES:
        raise GemGenerateError("the image model returned an unsupported image type")
    return data, content_type


# ---------- the tool ----------

def check_request(item: dict | None, setting, metal, style):
    """Validate a request; returns the reference photo."""
    if not item:
        raise GemGenerateError("stone not found")
    if item["status"] == "sold" or item["quantity"] <= 0:
        raise GemGenerateError("that stone is sold out")
    if setting not in SETTINGS or metal not in METALS or (style and style not in STYLES):
        raise GemGenerateError("unknown setting, metal or style")
    photo = reference_photo(item)
    if not photo:
        raise GemGenerateError("this stone has no photo yet, so a preview isn't possible")
    return photo


def preview_card(row: dict, item: dict) -> dict:
    """What the chat shows for one preview."""
    return {
        "id": row["id"],
        "url": get_storage().public_url(row["path"]),
        "label": describe(row["setting"], row["metal"], row["style"]),
        "item_id": item["id"],
        "agent_id": item["agent_id"],
        "item_name": item["name"],
        "price": item["price"],
        "status": item["status"],
        "quantity": item["quantity"],
    }


def generate(item: dict, setting: str, metal: str, style: str = "", context: dict | None = None):
    """
    Return (card, reused) for a preview of this stone, making it if needed.
    A new preview counts toward the GemGenerate limits; a saved one is free.
    Raises GemGenerateError with a reason the partner can pass on.
    """
    style = style or ""
    photo = check_request(item, setting, metal, style)
    model = current_model()
    key = cache_key(photo, setting, metal, style, model)
    saved = database.get_generated(item["id"], key)
    if saved:
        return preview_card(saved, item), True

    refusal = limits.check_image_allowed(context)
    if refusal == "off":
        raise GemGenerateError("AI previews are switched off right now")
    if refusal:
        raise GemGenerateError(limits.IMAGE_LIMIT_MESSAGES[refusal])

    path = None
    try:
        data, content_type = call_image_model(
            build_prompt(item, setting, metal, style), _data_url(photo), model
        )
        path = f"generated/{item['id']}/{uuid.uuid4().hex}.{IMAGE_TYPES[content_type]}"
        get_storage().put(path, data, content_type)
    except Exception as exc:
        # Our failure, not the customer's: give the preview back.
        limits.refund_image(context)
        if isinstance(exc, GemGenerateError):
            raise
        logger.exception("GemGenerate preview failed (model %s)", model)
        raise GemGenerateError(
            "the preview couldn't be saved" if path else "the preview couldn't be made right now"
        ) from exc
    row, created = database.save_generated({
        "item_id": item["id"], "key": key, "path": path, "setting": setting,
        "metal": metal, "style": style, "model": model,
    })
    if not created:
        get_storage().delete([path])
    return preview_card(row, item), False


def test_preview(item: dict, setting: str, metal: str, style: str, model: str) -> dict:
    """Admin tester: make a preview with any model, without saving it."""
    photo = check_request(item, setting, metal, style)
    data, content_type = call_image_model(
        build_prompt(item, setting, metal, style), _data_url(photo), model
    )
    return {
        "image": f"data:{content_type};base64,{base64.b64encode(data).decode()}",
        "label": describe(setting, metal, style),
        "model": model,
    }


TOOL = {
    "type": "function",
    "function": {
        "name": "gemgenerate",
        "description": (
            "Make an AI preview picture of one of your stones set in a piece "
            "of jewellery, when the customer wants to picture how it would "
            "look (e.g. 'how would it look in a ring?'). Uses the stone's "
            "real photo. It takes 10-30 seconds, so tell the customer you're "
            "sketching it. The picture is an AI preview, not the finished "
            "piece - say so. At most 2 per reply; only stones with photos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer", "description": "The stone's id."},
                "setting": {"type": "string", "enum": list(SETTINGS)},
                "metal": {
                    "type": "string",
                    "enum": list(METALS),
                    "description": "Pick one that flatters the stone if the customer didn't say.",
                },
                "style": {"type": "string", "enum": list(STYLES)},
            },
            "required": ["item_id", "setting", "metal"],
        },
    },
}
