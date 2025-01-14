from fastapi import FastAPI, File, UploadFile, Query, applications
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
import whisper
from whisper.utils import write_srt, write_vtt
from whisper import tokenizer
import os
from os import path
from pathlib import Path
import ffmpeg
from typing import BinaryIO, Union
import numpy as np
from io import StringIO
from threading import Lock
import torch

# import fastapi_offline_swagger_ui
import importlib.metadata
from pydub import AudioSegment
from pydantic import BaseModel
import sox
import numpy as np

SAMPLE_RATE = 16000
LANGUAGE_CODES = sorted(list(tokenizer.LANGUAGES.keys()))

projectMetadata = importlib.metadata.metadata("whisper-asr-webservice")
app = FastAPI(
    title=projectMetadata["Name"].title().replace("-", " "),
    description=projectMetadata["Summary"],
    version=projectMetadata["Version"],
    contact={"url": projectMetadata["Home-page"]},
    # swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    license_info={"name": "MIT License", "url": projectMetadata["License"]},
)

# assets_path = fastapi_offline_swagger_ui.__path__[0]
# if path.exists(assets_path + "/swagger-ui.css") and path.exists(assets_path + "/swagger-ui-bundle.js"):
#     app.mount("/assets", StaticFiles(directory=assets_path), name="static")
#     def swagger_monkey_patch(*args, **kwargs):
#         return get_swagger_ui_html(
#             *args,
#             **kwargs,
#             swagger_favicon_url="",
#             swagger_css_url="/assets/swagger-ui.css",
#             swagger_js_url="/assets/swagger-ui-bundle.js",
#         )
#     applications.get_swagger_ui_html = swagger_monkey_patch

# model_name = os.getenv("ASR_MODEL", "base")
model_name = "medium"
if torch.cuda.is_available():
    model = whisper.load_model(model_name).cuda()
else:
    model = whisper.load_model(model_name)
model_lock = Lock()


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def index():
    return "/docs"


@app.post("/asr", tags=["Endpoints"])
def transcribe(
    audio_file: UploadFile = File(...),
    task: Union[str, None] = Query(
        default="transcribe", enum=["transcribe", "translate"]
    ),
    language: Union[str, None] = Query(default="es", enum=LANGUAGE_CODES),
    output: Union[str, None] = Query(
        default="json", enum=["json", "vtt", "srt"]
    ),
):

    result = run_asr(audio_file.file, task, language)
    filename = audio_file.filename.split(".")[0]
    if output == "srt":
        srt_file = StringIO()
        write_srt(result["segments"], file=srt_file)
        srt_file.seek(0)
        return StreamingResponse(
            srt_file,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.srt"'
            },
        )
    elif output == "vtt":
        vtt_file = StringIO()
        write_vtt(result["segments"], file=vtt_file)
        vtt_file.seek(0)
        return StreamingResponse(
            vtt_file,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}.vtt"'
            },
        )
    else:
        return result


class TranscriptJob(BaseModel):
    interaction_id: str
    audio_format: str
    sample_rate: int
    base_path: str
    language: str


@app.post("/dual")
def dual_transcribe(job: TranscriptJob):
    result = run_dual_sox(job)
    return result


def run_dual_sox(job: TranscriptJob):
    options_dict = {"task": "transcribe", "language": f"{job.language}"}

    input_file = f"{job.base_path}/{job.interaction_id}.{job.audio_format}"

    # User usually talks first
    user_file = (
        f"{job.base_path}/split/{job.interaction_id}_USR.{job.audio_format}"
    )
    user_tfm = sox.Transformer()
    user_tfm.set_output_format(file_type="au", rate=8000, channels=1)
    user_tfm.remix(remix_dictionary={1: [1]})
    user = user_tfm.build(input_file, user_file)
    user_transcript = model.transcribe(user_file, **options_dict)

    agent_file = (
        f"{job.base_path}/split/{job.interaction_id}_AGT.{job.audio_format}"
    )
    agent_tfm = sox.Transformer()
    agent_tfm.set_output_format(file_type="au", rate=8000, channels=1)
    agent_tfm.remix(remix_dictionary={1: [2]})
    agent = agent_tfm.build(input_file, agent_file)
    agent_transcript = model.transcribe(agent_file, **options_dict)

    i = 0
    utterances = []
    # get the maximum of the lengths of both segment lists

    max_len = max(
        len(user_transcript["segments"]), len(agent_transcript["segments"])
    )
    for i in range(max_len):
        if i < len(user_transcript["segments"]):
            event = user_transcript["segments"][i]
            # push event to utterances list
            utterances.append(
                {
                    "text": event["text"],
                    "start": int(event["start"]) * 1000,
                    "end": event["end"],
                    "channel": 1,
                }
            )
        if i < len(agent_transcript["segments"]):
            event = agent_transcript["segments"][i]
            # push event to utterances list
            utterances.append(
                {
                    "text": event["text"],
                    "start": event["start"],
                    "end": event["end"],
                    "channel": 2,
                }
            )
    return {"utterances": utterances}


def run_dual(job: TranscriptJob):
    format = "au"
    base_path = "/Users/alexander/Downloads/calls"
    options_dict = {"task": "transcribe", "language": f"{job.language}"}
    audio = f"{job.base_path}/{job.interaction_id}.{job.audio_format}"
    stereo = AudioSegment.from_file(audio, format=format)
    monos = stereo.split_to_mono()
    out_left = f"{job.base_path}/split/{job.interaction_id}_L.{format}"
    mono_left = monos[0].export(out_left, format=format)
    out_right = f"{job.base_path}/split/{job.interaction_id}_R.{format}"
    mono_right = monos[1].export(out_right, format=format)

    result = model.transcribe(out_right, **options_dict)
    return result


@app.post("/detect-language", tags=["Endpoints"])
def language_detection(
    audio_file: UploadFile = File(...),
):

    # load audio and pad/trim it to fit 30 seconds
    audio = load_audio(audio_file.file)
    audio = whisper.pad_or_trim(audio)

    # make log-Mel spectrogram and move to the same device as the model
    mel = whisper.log_mel_spectrogram(audio).to(model.device)

    # detect the spoken language
    with model_lock:
        _, probs = model.detect_language(mel)
    detected_lang_code = max(probs, key=probs.get)

    result = {
        "detected_language": tokenizer.LANGUAGES[detected_lang_code],
        "langauge_code": detected_lang_code,
    }

    return result


def run_asr(
    file: BinaryIO, task: Union[str, None], language: Union[str, None]
):
    audio = load_audio(file)
    options_dict = {"task": task}
    if language:
        options_dict["language"] = language
    with model_lock:
        result = model.transcribe(audio, **options_dict)

    return result


def load_audio(file: BinaryIO, sr: int = SAMPLE_RATE):
    """
    Open an audio file object and read as mono waveform, resampling as necessary.
    Modified from https://github.com/openai/whisper/blob/main/whisper/audio.py to accept a file object
    Parameters
    ----------
    file: BinaryIO
        The audio file like object
    sr: int
        The sample rate to resample the audio if necessary
    Returns
    -------
    A NumPy array containing the audio waveform, in float32 dtype.
    """
    try:
        # This launches a subprocess to decode audio while down-mixing and resampling as necessary.
        # Requires the ffmpeg CLI and `ffmpeg-python` package to be installed.
        out, _ = (
            ffmpeg.input("pipe:", threads=0)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=sr)
            .run(
                cmd="ffmpeg",
                capture_stdout=True,
                capture_stderr=True,
                input=file.read(),
            )
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0
