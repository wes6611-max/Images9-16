import uuid
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from goblin import generate

app = FastAPI(title="Viral 9:16 Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK_DIR = Path("./workspace")
WORK_DIR.mkdir(exist_ok=True)
FRAMES_DIR = WORK_DIR / "frames"
FRAMES_DIR.mkdir(exist_ok=True)


@app.get("/")
async def serve_index():
    return FileResponse("index.html")


async def generate_single_image(prompt: str, output_path: Path, model: str = "goblin-flux"):
    try:
        await generate(prompt, model=model, output=str(output_path))
        return True
    except Exception as e:
        print(f"[Goblin AI] Echec : {e}")
        return False


def create_gif_from_frames(frame_paths, output_path: Path, fps: int = 8, width: int = 540, height: int = 960):
    if not frame_paths:
        raise ValueError("Liste d'images vide")

    concat_file = WORK_DIR / f"concat_{uuid.uuid4().hex}.txt"
    duration_per_frame = 12.0 / len(frame_paths)

    with open(concat_file, "w", encoding="utf-8") as f:
        for fp in frame_paths:
            f.write(f"file '{fp.resolve()}'\n")
            f.write(f"duration {duration_per_frame}\n")
        f.write(f"file '{frame_paths[-1].resolve()}'\n")

    palette_path = WORK_DIR / f"palette_{uuid.uuid4().hex}.png"
    filter_base = f"fps={fps},scale={width}:{height}:flags=lanczos"

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", f"{filter_base},palettegen",
        str(palette_path)
    ], check=True, capture_output=True)

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(palette_path),
        "-lavfi", f"{filter_base} [x]; [x][1:v] paletteuse",
        str(output_path)
    ], check=True, capture_output=True)

    concat_file.unlink(missing_ok=True)
    palette_path.unlink(missing_ok=True)
    return output_path


@app.post("/generate/image")
async def generate_image_endpoint(
    prompt: str = Form(...),
    style: str = Form("goblin-flux"),
    reference_image: Optional[UploadFile] = File(None),
):
    task_id = uuid.uuid4().hex
    out_path = WORK_DIR / f"img_{task_id}.png"

    if reference_image:
        print("[Info] reference_image recue mais non utilisee par Goblin AI")

    success = await generate_single_image(prompt, out_path, model=style)
    if not success:
        raise HTTPException(status_code=500, detail="Echec de la generation d'image")

    img = Image.open(out_path).convert("RGB")
    img = img.resize((1080, 1920), Image.LANCZOS)
    img.save(out_path)

    return FileResponse(out_path, media_type="image/png", filename=f"viral_{task_id}.png")


@app.post("/generate/gif")
async def generate_gif_endpoint(
    prompt: str = Form(...),
    style: str = Form("goblin-flux"),
    frame_count: int = Form(10),
):
    if frame_count < 5 or frame_count > 20:
        raise HTTPException(status_code=400, detail="frame_count doit etre entre 5 et 20")

    task_id = uuid.uuid4().hex
    frame_paths = []

    motion_hints = [
        "subtle movement, slight camera pan",
        "slight zoom in, dynamic lighting",
        "gentle rotation, soft motion blur",
        "cinematic drift, atmospheric change",
        "smooth transition, depth shift",
    ]

    for i in range(frame_count):
        hint = motion_hints[i % len(motion_hints)]
        frame_prompt = f"{prompt}, {hint}, frame {i+1}/{frame_count}, vertical 9:16 composition"
        fp = FRAMES_DIR / f"{task_id}_f{i:03d}.png"
        success = await generate_single_image(frame_prompt, fp, model=style)
        if success:
            img = Image.open(fp).convert("RGB")
            img = img.resize((1080, 1920), Image.LANCZOS)
            img.save(fp)
            frame_paths.append(fp)

    if len(frame_paths) < 3:
        raise HTTPException(status_code=500, detail="Pas assez d'images generees")

    gif_path = WORK_DIR / f"viral_{task_id}.gif"
    try:
        create_gif_from_frames(frame_paths, gif_path, fps=8, width=540, height=960)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Echec FFmpeg : {e.stderr.decode()[:500]}")

    for fp in frame_paths:
        fp.unlink(missing_ok=True)

    return FileResponse(gif_path, media_type="image/gif", filename=f"viral_{task_id}.gif")
