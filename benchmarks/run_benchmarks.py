from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import imagehash
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DEFAULT_API_URL = "http://127.0.0.1:3000"

IMAGEHASH_THRESHOLD = 10
SSIM_THRESHOLD = 0.55
TEMPLATE_THRESHOLD = 0.55
README_START = "<!-- BENCHMARKS:START -->"
README_END = "<!-- BENCHMARKS:END -->"


@dataclass(frozen=True)
class AttackSpec:
    attack_type: str
    severity: str
    output_ext: str
    apply: Callable[[Image.Image], Image.Image]
    is_combined: bool = False


@dataclass
class RegisteredImage:
    source_path: str
    image_id: str | None
    original_url: str | None
    secured_url: str | None
    secured_source_path: str | None
    upload_status: int | None
    upload_error: str | None


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    args = parse_args()
    images_dir = (root / args.images_dir).resolve()
    results_dir = (root / args.results_dir).resolve()
    generated_dir = results_dir / "generated"
    protected_dir = results_dir / "protected_sources"
    graphs_dir = results_dir / "graphs"

    image_paths = discover_images(images_dir, args.limit)
    if not image_paths:
        raise SystemExit(f"No benchmark images found in {images_dir}")

    validate_environment(args)

    results_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)
    protected_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir.mkdir(parents=True, exist_ok=True)

    token = args.access_token or os.getenv("BENCHMARK_ACCESS_TOKEN")
    cookies: dict[str, str] = {}

    if not args.skip_securepixel and not token:
        token, cookies = sign_in(args.api_url, args.email, args.password)

    attack_specs = build_attack_specs()
    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    registered_images: list[RegisteredImage] = []
    raw_records: list[dict[str, Any]] = []

    for index, image_path in enumerate(image_paths, start=1):
        print(f"[{index}/{len(image_paths)}] Preparing {image_path.name}")
        if not image_path.exists():
            print(f"Skipping {image_path.name}: file not found on disk")
            registered_images.append(RegisteredImage(str(image_path), None, None, None, None, 404, "File not found"))
            continue

        registered = register_image(
            image_path=image_path,
            api_url=args.api_url,
            token=token,
            cookies=cookies,
            skip_securepixel=args.skip_securepixel,
            skip_upload=args.skip_upload,
            protected_dir=protected_dir,
            delay_seconds=args.delay_seconds,
        )
        registered_images.append(registered)

        if not args.skip_securepixel and registered.upload_error:
            print(f"Skipping {image_path.name}: upload failed: {registered.upload_error}")
            continue

        try:
            reference = load_rgb(image_path)
        except FileNotFoundError:
            print(f"Skipping {image_path.name}: file disappeared before loading")
            continue
        protected_source_path = Path(registered.secured_source_path) if registered.secured_source_path else image_path
        try:
            protected_source = load_rgb(protected_source_path)
        except FileNotFoundError:
            print(f"Skipping {image_path.name}: protected source not found at {protected_source_path}")
            continue
        original_hashes = compute_hashes(reference)

        per_image_dir = generated_dir / image_path.stem
        per_image_dir.mkdir(parents=True, exist_ok=True)

        for attack in attack_specs:
            try:
                output_path = per_image_dir / f"{image_path.stem}__{attack.attack_type}__{safe_name(attack.severity)}.{attack.output_ext}"
                tampered = attack.apply(protected_source)
                save_image(tampered, output_path, attack.output_ext)
            except Exception as e:
                print(f"  Error generating attack {attack.attack_type}/{attack.severity} for {image_path.name}: {e}")
                continue

            try:
                baseline = run_baselines(
                    reference=reference,
                    tampered=tampered,
                    original_hashes=original_hashes,
                )
            except Exception as e:
                print(f"  Error running baselines for {image_path.name}/{attack.attack_type}: {e}")
                baseline = {"imagehash": {"detected": False, "error": str(e)}, "ssim": {"detected": False, "error": str(e)}, "opencv_template": {"detected": False, "error": str(e)}}

            securepixel = None
            if not args.skip_securepixel:
                try:
                    securepixel = run_securepixel_detection(
                        api_url=args.api_url,
                        token=token,
                        cookies=cookies,
                        image_path=output_path,
                        delay_seconds=args.delay_seconds,
                    )
                except Exception as e:
                    print(f"  Error in SecurePixel detection for {image_path.name}/{attack.attack_type}: {e}")
                    securepixel = {"detected": False, "layer": None, "confidence_or_similarity": None, "time_ms": 0, "status_code": 0, "error": str(e)}

            raw_records.append(
                {
                    "source_image": str(image_path.relative_to(root)),
                    "protected_source": str(protected_source_path.relative_to(root)) if protected_source_path.exists() else None,
                    "tampered_image": str(output_path.relative_to(root)),
                    "registered_image_id": registered.image_id,
                    "attack_type": attack.attack_type,
                    "severity": attack.severity,
                    "is_combined_attack": attack.is_combined,
                    "securepixel": securepixel,
                    "baselines": baseline,
                }
            )

    payload = {
        "metadata": {
            "suite": "SecurePixel detection benchmark",
            "started_at": run_started_at,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api_url": args.api_url,
            "images_dir": str(images_dir),
            "image_count": len(image_paths),
            "attack_count_per_image": len(attack_specs),
            "securepixel_skipped": args.skip_securepixel,
            "upload_skipped": args.skip_upload,
            "thresholds": {
                "imagehash_hamming_distance": IMAGEHASH_THRESHOLD,
                "ssim": SSIM_THRESHOLD,
                "opencv_template": TEMPLATE_THRESHOLD,
            },
        },
        "registered_images": [asdict(item) for item in registered_images],
        "records": raw_records,
    }

    raw_results_path = results_dir / "raw_results.json"
    raw_results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = summarize(payload)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown_report(results_dir / "summary.md", summary)
    generate_graphs(summary, raw_records, graphs_dir)
    update_readme(root / "README.md", summary)

    print(f"Raw results written to {raw_results_path}")
    print(f"Graphs written to {graphs_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark SecurePixel detection against image tampering attacks.")
    parser.add_argument("--api-url", default=os.getenv("BENCHMARK_API_URL") or api_url_from_env())
    parser.add_argument("--email", default=os.getenv("BENCHMARK_EMAIL"))
    parser.add_argument("--password", default=os.getenv("BENCHMARK_PASSWORD"))
    parser.add_argument("--access-token", default=os.getenv("BENCHMARK_ACCESS_TOKEN"))
    parser.add_argument("--images-dir", default="benchmark-images")
    parser.add_argument("--results-dir", default="benchmarks/results")
    parser.add_argument("--limit", type=int, default=int(os.getenv("BENCHMARK_LIMIT", "0")) or None)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.getenv("BENCHMARK_DELAY_SECONDS", "9.1")),
        help="Delay between SecurePixel API calls. Default keeps requests below 400/hour.",
    )
    parser.add_argument("--skip-securepixel", action="store_true", help="Only generate attacks and baseline results.")
    parser.add_argument("--skip-upload", action="store_true", help="Do not upload originals before detection.")
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def api_url_from_env() -> str:
    port = os.getenv("PORT")
    if port:
        return f"http://127.0.0.1:{port}"
    return DEFAULT_API_URL


def validate_environment(args: argparse.Namespace) -> None:
    if args.skip_securepixel:
        return

    required = [
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
        "AI_SERVICE_URL",
        "AI_SERVICE_API_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "UPSTASH_VECTOR_REST_URL",
        "UPSTASH_VECTOR_REST_TOKEN",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if not args.api_url:
        missing.append("BENCHMARK_API_URL or PORT")
    if not args.access_token and not (args.email and args.password):
        missing.append("BENCHMARK_ACCESS_TOKEN or BENCHMARK_EMAIL/BENCHMARK_PASSWORD")
    if missing:
        raise SystemExit(
            "Missing required benchmark environment variables:\n"
            + "\n".join(f"- {key}" for key in missing)
        )


def discover_images(images_dir: Path, limit: int | None) -> list[Path]:
    images = sorted(
        path for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    return images[:limit] if limit else images


def build_attack_specs() -> list[AttackSpec]:
    specs: list[AttackSpec] = []

    for pct in (25, 50, 75):
        specs.append(AttackSpec("crop", f"{pct}_percent_center", "jpg", lambda img, pct=pct: crop_center(img, pct)))

    for pct in (25, 50, 200):
        specs.append(AttackSpec("resize", f"{pct}_percent", "jpg", lambda img, pct=pct: resize_percent(img, pct)))

    for quality in (90, 70, 50, 30):
        specs.append(AttackSpec("jpeg_compression", f"quality_{quality}", "jpg", lambda img, quality=quality: jpeg_roundtrip(img, quality)))

    for factor in (0.70, 1.30):
        specs.append(AttackSpec("brightness", f"factor_{factor}", "jpg", lambda img, factor=factor: enhance(img, ImageEnhance.Brightness, factor)))

    for factor in (0.70, 1.40):
        specs.append(AttackSpec("contrast", f"factor_{factor}", "jpg", lambda img, factor=factor: enhance(img, ImageEnhance.Contrast, factor)))

    for factor in (0.50, 1.50):
        specs.append(AttackSpec("saturation", f"factor_{factor}", "jpg", lambda img, factor=factor: enhance(img, ImageEnhance.Color, factor)))

    specs.append(AttackSpec("format_conversion", "png_to_jpeg", "jpg", lambda img: img.copy()))
    specs.append(AttackSpec("format_conversion", "jpeg_to_png", "png", lambda img: img.copy()))
    specs.append(AttackSpec("flip", "horizontal", "jpg", lambda img: img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
    specs.append(AttackSpec("flip", "vertical", "jpg", lambda img: img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)))

    for sigma in (5, 12, 24):
        specs.append(AttackSpec("gaussian_noise", f"sigma_{sigma}", "jpg", lambda img, sigma=sigma: add_gaussian_noise(img, sigma)))

    specs.append(AttackSpec("screenshot_simulation", "quality_85_blur_0.6", "jpg", screenshot_simulation))

    for region in ("center", "corner"):
        specs.append(AttackSpec("generative_fill_simulation", f"{region}_patch", "jpg", lambda img, region=region: inpaint_patch(img, region)))

    for scale in (2, 4):
        specs.append(AttackSpec("ai_upscale_simulation", f"{scale}x_bicubic", "jpg", lambda img, scale=scale: upscale_bicubic(img, scale)))

    specs.extend(
        [
            AttackSpec(
                "combined_attack",
                "jpeg70_resize50_noise12",
                "jpg",
                lambda img: add_gaussian_noise(resize_percent(jpeg_roundtrip(img, 70), 50), 12),
                is_combined=True,
            ),
            AttackSpec(
                "combined_attack",
                "crop75_contrast140_jpeg50",
                "jpg",
                lambda img: jpeg_roundtrip(enhance(crop_center(img, 75), ImageEnhance.Contrast, 1.4), 50),
                is_combined=True,
            ),
            AttackSpec(
                "combined_attack",
                "screenshot_flip_brightness70",
                "jpg",
                lambda img: enhance(
                    screenshot_simulation(img).transpose(Image.Transpose.FLIP_LEFT_RIGHT),
                    ImageEnhance.Brightness,
                    0.70,
                ),
                is_combined=True,
            ),
        ]
    )

    return specs


def load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def save_image(image: Image.Image, path: Path, ext: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if ext.lower() in {"jpg", "jpeg"}:
        image.convert("RGB").save(path, format="JPEG", quality=95, optimize=True)
    elif ext.lower() == "png":
        image.convert("RGB").save(path, format="PNG", optimize=True)
    else:
        image.save(path)


def crop_center(image: Image.Image, pct: int) -> Image.Image:
    width, height = image.size
    new_w = max(1, int(width * pct / 100))
    new_h = max(1, int(height * pct / 100))
    left = (width - new_w) // 2
    top = (height - new_h) // 2
    return image.crop((left, top, left + new_w, top + new_h))


def resize_percent(image: Image.Image, pct: int) -> Image.Image:
    width, height = image.size
    return image.resize(
        (max(1, int(width * pct / 100)), max(1, int(height * pct / 100))),
        Image.Resampling.LANCZOS,
    )


def jpeg_roundtrip(image: Image.Image, quality: int) -> Image.Image:
    import io

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def enhance(image: Image.Image, enhancer: type, factor: float) -> Image.Image:
    return enhancer(image).enhance(factor)


def add_gaussian_noise(image: Image.Image, sigma: int) -> Image.Image:
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    noise = np.random.default_rng(42).normal(0, sigma, arr.shape)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def screenshot_simulation(image: Image.Image) -> Image.Image:
    degraded = jpeg_roundtrip(image, 85)
    return degraded.filter(ImageFilter.GaussianBlur(radius=0.6))


def inpaint_patch(image: Image.Image, region: str) -> Image.Image:
    arr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    height, width = arr.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    patch_w = max(8, width // 5)
    patch_h = max(8, height // 5)

    if region == "corner":
        x1, y1 = width - patch_w - max(2, width // 30), max(2, height // 30)
    else:
        x1, y1 = (width - patch_w) // 2, (height - patch_h) // 2

    mask[y1:y1 + patch_h, x1:x1 + patch_w] = 255
    inpainted = cv2.inpaint(arr, mask, 3, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))


def upscale_bicubic(image: Image.Image, scale: int) -> Image.Image:
    width, height = image.size
    return image.resize((width * scale, height * scale), Image.Resampling.BICUBIC)


def sign_in(api_url: str, email: str, password: str) -> tuple[str, dict[str, str]]:
    status, body, headers = http_json(
        f"{api_url.rstrip('/')}/auth/signin",
        {"email": email, "password": password},
    )
    if status >= 400:
        raise RuntimeError(f"Signin failed with {status}: {body}")
    access_token = body.get("accessToken")
    if not access_token:
        raise RuntimeError("Signin response did not contain accessToken")
    cookies = parse_set_cookie(headers)
    return access_token, cookies


def register_image(
    image_path: Path,
    api_url: str,
    token: str | None,
    cookies: dict[str, str],
    skip_securepixel: bool,
    skip_upload: bool,
    protected_dir: Path,
    delay_seconds: float,
) -> RegisteredImage:
    if skip_securepixel or skip_upload:
        return RegisteredImage(str(image_path), None, None, None, None, None, None)

    started = time.perf_counter()
    try:
        status, body = http_multipart(
            url=f"{api_url.rstrip('/')}/upload",
            field_name="image",
            file_path=image_path,
            token=token,
            cookies=cookies,
        )
    except FileNotFoundError:
        return RegisteredImage(str(image_path), None, None, None, None, 404, f"File not found: {image_path.name}")
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if status >= 400:
        throttle(delay_seconds)
        return RegisteredImage(str(image_path), None, None, None, None, status, f"{body} ({elapsed_ms}ms)")

    image_id = body.get("image_id")
    urls = body.get("urls") or {}
    secured_url = urls.get("secured")
    original_url = urls.get("original")
    secured_source_path = None

    if secured_url:
        target = protected_dir / f"{image_path.stem}__secured.png"
        try:
            download_file(secured_url, target)
            secured_source_path = str(target)
        except Exception as error:
            print(f"Warning: failed to download secured image for {image_path.name}: {error}")

    throttle(delay_seconds)
    return RegisteredImage(str(image_path), image_id, original_url, secured_url, secured_source_path, status, None)


def run_securepixel_detection(
    api_url: str,
    token: str | None,
    cookies: dict[str, str],
    image_path: Path,
    delay_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    status, body = http_multipart(
        url=f"{api_url.rstrip('/')}/detect",
        field_name="image",
        file_path=image_path,
        token=token,
        cookies=cookies,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    throttle(delay_seconds)
    detected = is_securepixel_detected(status, body)
    layer = classify_securepixel_layer(body)
    score = extract_securepixel_score(body)
    return {
        "detected": detected,
        "layer": layer,
        "confidence_or_similarity": score,
        "time_ms": elapsed_ms,
        "status_code": status,
        "response": body,
    }


def throttle(delay_seconds: float) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def is_securepixel_detected(status: int, body: dict[str, Any]) -> bool:
    if status == 429:
        return False
    message = str(body.get("message", "")).lower()
    # Negative case: "No duplicates found. Image is unique." must NOT match
    if "no duplicates found" in message:
        return False
    if "duplicate detected" in message or "suspected derivative detected" in message or "own registered image" in message:
        return True
    return False


def classify_securepixel_layer(body: dict[str, Any]) -> str | None:
    method = str(body.get("method", "")).lower()
    message = str(body.get("message", "")).lower()
    # Layer 1 - Watermark
    if "layer 1" in message or "watermarking" in method:
        return "watermark"
    # Layer 2 - Perceptual Hash
    if "layer 2" in message or "perceptual hashing" in method:
        return "perceptual_hash"
    # Layer 3 - CLIP Embedding
    if "layer 3" in message or "clip embedding" in method:
        return "embedding_similarity"
    return None


def extract_securepixel_score(body: dict[str, Any]) -> float | str | None:
    if "similarity_score" in body:
        return body["similarity_score"]
    return body.get("confidence")


def compute_hashes(image: Image.Image) -> dict[str, imagehash.ImageHash]:
    return {
        "average_hash": imagehash.average_hash(image),
        "perceptual_hash": imagehash.phash(image),
        "difference_hash": imagehash.dhash(image),
        "wavelet_hash": imagehash.whash(image),
    }


def run_baselines(
    reference: Image.Image,
    tampered: Image.Image,
    original_hashes: dict[str, imagehash.ImageHash],
) -> dict[str, Any]:
    tampered_hashes = compute_hashes(tampered)
    hash_distances = {
        name: int(original_hashes[name] - tampered_hashes[name])
        for name in original_hashes
    }
    imagehash_detected = any(distance <= IMAGEHASH_THRESHOLD for distance in hash_distances.values())
    ssim_score = compute_ssim(reference, tampered)
    template_score = compute_template_score(reference, tampered)

    return {
        "imagehash": {
            "detected": imagehash_detected,
            "threshold": IMAGEHASH_THRESHOLD,
            "distances": hash_distances,
            "best_distance": min(hash_distances.values()),
        },
        "ssim": {
            "detected": ssim_score >= SSIM_THRESHOLD,
            "threshold": SSIM_THRESHOLD,
            "score": ssim_score,
        },
        "opencv_template": {
            "detected": template_score >= TEMPLATE_THRESHOLD,
            "threshold": TEMPLATE_THRESHOLD,
            "score": template_score,
        },
    }


def compute_ssim(reference: Image.Image, tampered: Image.Image) -> float:
    ref = pil_to_gray_array(reference.resize((256, 256), Image.Resampling.LANCZOS))
    cmp = pil_to_gray_array(tampered.resize((256, 256), Image.Resampling.LANCZOS))
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_x = ref.mean()
    mu_y = cmp.mean()
    sigma_x = ref.var()
    sigma_y = cmp.var()
    sigma_xy = ((ref - mu_x) * (cmp - mu_y)).mean()
    numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
    denominator = (mu_x ** 2 + mu_y ** 2 + c1) * (sigma_x + sigma_y + c2)
    return float(numerator / denominator) if denominator else 0.0


def compute_template_score(reference: Image.Image, tampered: Image.Image) -> float:
    ref = pil_to_gray_array(reference)
    cmp = pil_to_gray_array(tampered)
    max_dim = 512
    ref = resize_array_max(ref, max_dim)
    cmp = resize_array_max(cmp, max_dim)

    if ref.shape[0] < cmp.shape[0] or ref.shape[1] < cmp.shape[1]:
        search, template = cmp, ref
    else:
        search, template = ref, cmp

    if template.shape[0] < 4 or template.shape[1] < 4:
        return 0.0
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        template = cv2.resize(template, (search.shape[1], search.shape[0]))

    result = cv2.matchTemplate(search.astype(np.float32), template.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    return float(np.nanmax(result)) if result.size else 0.0


def pil_to_gray_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L")).astype(np.float32)


def resize_array_max(arr: np.ndarray, max_dim: int) -> np.ndarray:
    height, width = arr.shape[:2]
    scale = min(1.0, max_dim / max(height, width))
    if scale == 1.0:
        return arr
    return cv2.resize(arr, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)


def http_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, str]]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8")), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, parse_json_body(error.read()), dict(error.headers)


def http_multipart(
    url: str,
    field_name: str,
    file_path: Path,
    token: str | None,
    cookies: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    boundary = f"----SecurePixelBenchmark{int(time.time() * 1000)}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookies:
        headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, parse_json_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, parse_json_body(error.read())
    except Exception as error:
        return 0, {"error": str(error)}


def parse_json_body(raw: bytes) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
        return json.loads(decoded) if decoded else {}
    except Exception:
        return {"raw": raw.decode("utf-8", errors="replace")}


def parse_set_cookie(headers: dict[str, str]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == "set-cookie":
            first = value.split(";", 1)[0]
            if "=" in first:
                name, cookie_value = first.split("=", 1)
                cookies[name] = cookie_value
    return cookies


def download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload["records"]
    systems = ["securepixel", "imagehash", "ssim", "opencv_template"]
    by_attack: dict[str, dict[str, Any]] = {}

    attack_types = sorted({record["attack_type"] for record in records})
    for attack_type in attack_types:
        attack_records = [record for record in records if record["attack_type"] == attack_type]
        row: dict[str, Any] = {"count": len(attack_records)}
        for system in systems:
            row[system] = detection_rate(attack_records, system)
        by_attack[attack_type] = row

    leaderboard = {
        system: detection_rate(records, system)
        for system in systems
    }

    layer_counts: dict[str, int] = {}
    securepixel_detected = [
        record for record in records
        if record.get("securepixel") and record["securepixel"].get("detected")
    ]
    for record in securepixel_detected:
        layer = record["securepixel"].get("layer") or "unknown"
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    by_severity = summarize_by_severity(records)
    combined = {
        "single_attack": detection_rate([record for record in records if not record["is_combined_attack"]], "securepixel"),
        "combined_attack": detection_rate([record for record in records if record["is_combined_attack"]], "securepixel"),
    }

    generative_fill = {
        severity: detection_rate([record for record in records if record["attack_type"] == "generative_fill_simulation" and record["severity"] == severity], "securepixel")
        for severity in sorted({record["severity"] for record in records if record["attack_type"] == "generative_fill_simulation"})
    }

    return {
        "metadata": payload["metadata"],
        "by_attack_type": by_attack,
        "leaderboard": dict(sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)),
        "securepixel_layer_counts": layer_counts,
        "by_severity": by_severity,
        "generative_fill": generative_fill,
        "combined_vs_single": combined,
    }


def detection_rate(records: list[dict[str, Any]], system: str) -> float:
    if not records:
        return 0.0
    detected = 0
    for record in records:
        if system == "securepixel":
            securepixel_result = record.get("securepixel") or {}
            detected += int(bool(securepixel_result.get("detected")))
        else:
            detected += int(bool(record["baselines"][system]["detected"]))
    return round(detected / len(records), 4)


def summarize_by_severity(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for attack_type in ("jpeg_compression", "crop"):
        output[attack_type] = {}
        severities = sorted({record["severity"] for record in records if record["attack_type"] == attack_type})
        for severity in severities:
            output[attack_type][severity] = detection_rate(
                [record for record in records if record["attack_type"] == attack_type and record["severity"] == severity],
                "securepixel",
            )
    return output


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# SecurePixel Benchmark Summary",
        "",
        "## Detection Rate by Attack Type",
        "",
        "| Attack type | SecurePixel | ImageHash | SSIM | OpenCV template | Samples |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for attack_type, row in summary["by_attack_type"].items():
        lines.append(
            f"| {attack_type} | {pct(row['securepixel'])} | {pct(row['imagehash'])} | "
            f"{pct(row['ssim'])} | {pct(row['opencv_template'])} | {row['count']} |"
        )

    lines.extend(["", "## Leaderboard", "", "| Rank | System | Detection rate |", "|---:|---|---:|"])
    for rank, (system, rate) in enumerate(summary["leaderboard"].items(), start=1):
        lines.append(f"| {rank} | {system} | {pct(rate)} |")

    lines.extend(["", "## SecurePixel Layer Contribution", "", "| Layer | Count |", "|---|---:|"])
    for layer, count in summary["securepixel_layer_counts"].items():
        lines.append(f"| {layer} | {count} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_readme(path: Path, summary: dict[str, Any]) -> None:
    current = path.read_text(encoding="utf-8")
    section = render_readme_benchmark_section(summary)

    if README_START in current and README_END in current:
        before = current.split(README_START, 1)[0]
        after = current.split(README_END, 1)[1]
        updated = before + section + after
    else:
        start = current.find("## Benchmarks")
        next_heading = current.find("\n## Environment Variables", start)
        if start == -1 or next_heading == -1:
            updated = current.rstrip() + "\n\n" + section + "\n"
        else:
            updated = current[:start] + section + current[next_heading:]

    path.write_text(updated, encoding="utf-8")


def render_readme_benchmark_section(summary: dict[str, Any]) -> str:
    metadata = summary["metadata"]
    table_lines = [
        "| Attack type | SecurePixel | ImageHash | SSIM | OpenCV template | Samples |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for attack_type, row in summary["by_attack_type"].items():
        table_lines.append(
            f"| {attack_type} | {pct(row['securepixel'])} | {pct(row['imagehash'])} | "
            f"{pct(row['ssim'])} | {pct(row['opencv_template'])} | {row['count']} |"
        )

    leaderboard_lines = ["| Rank | System | Detection rate |", "|---:|---|---:|"]
    for rank, (system, rate) in enumerate(summary["leaderboard"].items(), start=1):
        leaderboard_lines.append(f"| {rank} | {system} | {pct(rate)} |")

    layer_lines = ["| Layer | Detected samples |", "|---|---:|"]
    if summary["securepixel_layer_counts"]:
        for layer, count in summary["securepixel_layer_counts"].items():
            layer_lines.append(f"| {layer} | {count} |")
    else:
        layer_lines.append("| none | 0 |")

    return "\n".join(
        [
            README_START,
            "## Benchmarks",
            "",
            "SecurePixel includes a reproducible benchmark suite for measuring the detection pipeline against common image tampering attacks and classical baseline systems.",
            "",
            "### Latest benchmark run",
            "",
            f"- Completed at: `{metadata.get('completed_at', 'unknown')}`",
            f"- Images processed: `{metadata.get('image_count', 0)}`",
            f"- Attack variants per image: `{metadata.get('attack_count_per_image', 0)}`",
            f"- SecurePixel API URL: `{metadata.get('api_url', 'unknown')}`",
            f"- SecurePixel skipped: `{metadata.get('securepixel_skipped', False)}`",
            "",
            "### Methodology",
            "",
            "The benchmark reads original images from `benchmark-images/`, uploads each original through `/upload`, generates tampered variants, runs those variants through `/detect`, and compares SecurePixel against ImageHash, SSIM, and OpenCV template matching baselines.",
            "",
            "Attack coverage includes crop, resize, JPEG compression, brightness, contrast, saturation, format conversion, horizontal and vertical flips, gaussian noise, screenshot simulation, OpenCV inpainting as a generative-fill proxy, bicubic upscaling, and combination attacks.",
            "",
            "SecurePixel is measured through the actual REST API. Each record includes detection status, layer, confidence or similarity score, latency, attack type, and severity. Baselines are measured locally against the same generated tampered images.",
            "",
            f"- ImageHash threshold: Hamming distance <= `{metadata['thresholds']['imagehash_hamming_distance']}`",
            f"- SSIM threshold: score >= `{metadata['thresholds']['ssim']}`",
            f"- OpenCV template threshold: score >= `{metadata['thresholds']['opencv_template']}`",
            "",
            "Raw reusable output is written to `benchmarks/results/raw_results.json`. Machine-readable summary output is written to `benchmarks/results/summary.json`.",
            "",
            "### Detection rate by attack type",
            "",
            *table_lines,
            "",
            "### Leaderboard",
            "",
            *leaderboard_lines,
            "",
            "### SecurePixel layer contribution",
            "",
            *layer_lines,
            "",
            "### Graphs",
            "",
            "![SecurePixel detection rate by attack type](benchmarks/results/graphs/securepixel_detection_rate_by_attack.png)",
            "",
            "![SecurePixel vs baselines](benchmarks/results/graphs/head_to_head_detection_rate.png)",
            "",
            "![SecurePixel layer contribution](benchmarks/results/graphs/securepixel_layer_contribution.png)",
            "",
            "![SecurePixel confidence distribution](benchmarks/results/graphs/securepixel_confidence_distribution.png)",
            "",
            "![Detection rate vs severity](benchmarks/results/graphs/detection_rate_vs_severity.png)",
            "",
            "![Generative fill detection rate](benchmarks/results/graphs/generative_fill_detection_rate.png)",
            "",
            "![Combined vs single attack detection rate](benchmarks/results/graphs/combined_vs_single_attack_detection_rate.png)",
            "",
            "### Interpretation",
            "",
            render_interpretation(summary),
            "",
            "### Running the benchmark",
            "",
            "Install Python benchmark dependencies:",
            "",
            "```bash",
            "pip install -r benchmarks/requirements.txt",
            "```",
            "",
            "Run the full suite:",
            "",
            "```bash",
            "BENCHMARK_API_URL=http://127.0.0.1:3000 \\",
            "BENCHMARK_EMAIL=<verified-user-email> \\",
            "BENCHMARK_PASSWORD=<verified-user-password> \\",
            "npm run benchmark",
            "```",
            "",
            "On Windows PowerShell:",
            "",
            "```powershell",
            "$env:BENCHMARK_API_URL=\"http://127.0.0.1:3000\"",
            "$env:BENCHMARK_EMAIL=\"<verified-user-email>\"",
            "$env:BENCHMARK_PASSWORD=\"<verified-user-password>\"",
            "npm run benchmark",
            "```",
            "",
            "Optional controls:",
            "",
            "```bash",
            "npm run benchmark -- --limit 10",
            "npm run benchmark -- --skip-securepixel",
            "npm run benchmark -- --access-token <jwt-access-token>",
            "npm run benchmark -- --delay-seconds 9.1",
            "```",
            "",
            "The default delay of `9.1` seconds keeps SecurePixel API calls below 400 requests per hour.",
            README_END,
            "",
        ]
    )


def render_interpretation(summary: dict[str, Any]) -> str:
    by_attack = summary["by_attack_type"]
    securepixel_rates = {
        attack: row["securepixel"]
        for attack, row in by_attack.items()
    }
    best_attack, best_rate = max(securepixel_rates.items(), key=lambda item: item[1], default=("none", 0))
    worst_attack, worst_rate = min(securepixel_rates.items(), key=lambda item: item[1], default=("none", 0))
    leaderboard = list(summary["leaderboard"].items())
    leader_name, leader_rate = leaderboard[0] if leaderboard else ("none", 0)
    securepixel_rate = summary["leaderboard"].get("securepixel", 0)
    generative_rates = summary.get("generative_fill", {})
    combined_rates = summary.get("combined_vs_single", {})
    generative_avg = sum(generative_rates.values()) / len(generative_rates) if generative_rates else 0
    combined_rate = combined_rates.get("combined_attack", 0)
    single_rate = combined_rates.get("single_attack", 0)

    layer_counts = summary.get("securepixel_layer_counts", {})
    dominant_layer = max(layer_counts.items(), key=lambda item: item[1])[0] if layer_counts else "none"

    comparison = (
        f"The top overall system in this run was `{leader_name}` at {pct(leader_rate)}. "
        f"SecurePixel finished at {pct(securepixel_rate)} overall."
    )
    if leader_name == "securepixel":
        comparison = f"SecurePixel led this benchmark run with an overall detection rate of {pct(securepixel_rate)}."

    return (
        f"{comparison} SecurePixel performed best on `{best_attack}` at {pct(best_rate)} and struggled most on "
        f"`{worst_attack}` at {pct(worst_rate)}. The dominant SecurePixel layer was `{dominant_layer}`, which shows "
        "which part of the layered pipeline carried most detections in this run. "
        f"Generative fill simulation averaged {pct(generative_avg)}, which should be treated as a hard case because it changes image content rather than only metadata, encoding, color, or scale. "
        f"Combined attacks detected at {pct(combined_rate)} compared with {pct(single_rate)} for single attacks, showing how detection degrades when edits are stacked."
    )


def generate_graphs(summary: dict[str, Any], records: list[dict[str, Any]], graphs_dir: Path) -> None:
    graphs_dir.mkdir(parents=True, exist_ok=True)
    plot_securepixel_by_attack(summary, graphs_dir / "securepixel_detection_rate_by_attack.png")
    plot_head_to_head(summary, graphs_dir / "head_to_head_detection_rate.png")
    plot_layer_contribution(summary, graphs_dir / "securepixel_layer_contribution.png")
    plot_confidence_distribution(records, graphs_dir / "securepixel_confidence_distribution.png")
    plot_severity(summary, graphs_dir / "detection_rate_vs_severity.png")
    plot_generative_fill(summary, graphs_dir / "generative_fill_detection_rate.png")
    plot_combined_vs_single(summary, graphs_dir / "combined_vs_single_attack_detection_rate.png")


def plot_securepixel_by_attack(summary: dict[str, Any], path: Path) -> None:
    attacks = list(summary["by_attack_type"].keys())
    rates = [summary["by_attack_type"][attack]["securepixel"] for attack in attacks]
    bar_chart(attacks, rates, "SecurePixel detection rate by attack type", "Detection rate", path)


def plot_head_to_head(summary: dict[str, Any], path: Path) -> None:
    attacks = list(summary["by_attack_type"].keys())
    systems = ["securepixel", "imagehash", "ssim", "opencv_template"]
    x = np.arange(len(attacks))
    width = 0.2
    plt.figure(figsize=(max(12, len(attacks) * 0.75), 6))
    for idx, system in enumerate(systems):
        plt.bar(
            x + (idx - 1.5) * width,
            [summary["by_attack_type"][attack][system] for attack in attacks],
            width,
            label=system,
        )
    plt.xticks(x, attacks, rotation=45, ha="right")
    plt.ylim(0, 1)
    plt.ylabel("Detection rate")
    plt.title("SecurePixel vs baseline systems")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_layer_contribution(summary: dict[str, Any], path: Path) -> None:
    layers = list(summary["securepixel_layer_counts"].keys()) or ["none"]
    counts = [summary["securepixel_layer_counts"].get(layer, 0) for layer in layers]
    bar_chart(layers, counts, "SecurePixel per-layer contribution", "Detected samples", path, ylim=None)


def plot_confidence_distribution(records: list[dict[str, Any]], path: Path) -> None:
    values: list[float] = []
    for record in records:
        result = record.get("securepixel")
        if not result or not result.get("detected"):
            continue
        score = result.get("confidence_or_similarity")
        if isinstance(score, (int, float)):
            values.append(float(score))
        elif isinstance(score, str):
            normalized = score.strip().lower().replace("%", "")
            if normalized.isdigit():
                values.append(float(normalized) / 100)
            elif normalized == "high":
                values.append(0.95)
            elif normalized == "medium":
                values.append(0.90)
    plt.figure(figsize=(8, 5))
    if values:
        plt.hist(values, bins=10, range=(0, 1), color="#0F766E", edgecolor="white")
    plt.title("SecurePixel confidence and similarity distribution")
    plt.xlabel("Normalized confidence / similarity")
    plt.ylabel("Samples")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_severity(summary: dict[str, Any], path: Path) -> None:
    plt.figure(figsize=(9, 5))
    for attack_type, severities in summary["by_severity"].items():
        labels = list(severities.keys())
        rates = list(severities.values())
        plt.plot(labels, rates, marker="o", label=attack_type)
    plt.ylim(0, 1)
    plt.ylabel("SecurePixel detection rate")
    plt.title("Detection rate vs severity")
    plt.xticks(rotation=20, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_generative_fill(summary: dict[str, Any], path: Path) -> None:
    labels = list(summary["generative_fill"].keys())
    rates = list(summary["generative_fill"].values())
    bar_chart(labels, rates, "Generative fill simulation detection rate", "Detection rate", path)


def plot_combined_vs_single(summary: dict[str, Any], path: Path) -> None:
    labels = list(summary["combined_vs_single"].keys())
    rates = list(summary["combined_vs_single"].values())
    bar_chart(labels, rates, "Combined attack vs single attack detection rate", "Detection rate", path)


def bar_chart(labels: list[str], values: list[float], title: str, ylabel: str, path: Path, ylim: tuple[float, float] | None = (0, 1)) -> None:
    plt.figure(figsize=(max(8, len(labels) * 0.75), 5))
    plt.bar(labels, values, color="#0F766E")
    if ylim:
        plt.ylim(*ylim)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


if __name__ == "__main__":
    main()
