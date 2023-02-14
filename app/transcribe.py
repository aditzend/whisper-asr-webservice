import logging
import json
import whisper

# from whisper.utils import write_srt, write_vtt
import whisper
import sox
import os
from os import path
from pathlib import Path
from typing import BinaryIO, Union
import numpy as np
from io import StringIO
from threading import Lock
import torch
from dotenv import load_dotenv
import requests
import alert
from rabbit import PubSub
import time

load_dotenv()

rabbitmq_host = os.getenv("RABBITMQ_HOST") or ""
rabbitmq_port = os.getenv("RABBITMQ_PORT") or ""
rabbitmq_transcript_exchange = os.getenv("RABBITMQ_TRANSCRIPT_EXCHANGE") or ""

analytics_manager_url = os.getenv("ANALYTICS_MANAGER_URL") or ""

SAMPLE_RATE = 16000
# LANGUAGE_CODES = sorted(list(tokenizer.LANGUAGES.keys()))
model_name = os.getenv("WHISPER_MODEL_NAME") or "medium"
if torch.cuda.is_available():
    model = whisper.load_model(model_name, download_root="/models").cuda()
else:
    model = whisper.load_model(model_name, download_root="/models")
    model_lock = Lock()

logger = logging.getLogger(__name__)

rabbit = PubSub()


def test(ch, method, properties, body):
    logger.warning(" [x] %r:%r" % (method.routing_key, body.decode()))
    time.sleep(10)
    logger.error(method)
    ch.basic_ack(delivery_tag=method.delivery_tag)
    # ch.basic_ack()


def run_dual_sox(ch, method, properties, body):
    # logger.info(" [x] %r:%r" % (method.routing_key, body.decode()))
    message = json.loads(body.decode())
    job = message["data"]
    try:
        options_dict = {"task": "transcribe", "language": job["asr_language"]}
        stem = (
            job["campaign_name"]
            + "_"
            + job["segment_number"]
            + "_"
            + job["interaction_id"]
        )

        input_file = job["base_path"] + "/" + stem + "." + job["audio_format"]

        user_file = (
            f"{job['base_path']}/split/{stem}_USR.{job['audio_format']}"
        )
        agent_file = (
            f"{job['base_path']}/split/{stem}_AGT.{job['audio_format']}"
        )
        user_tfm = sox.Transformer()
        user_tfm.set_output_format(file_type="au", rate=8000, channels=1)
        user_tfm.remix(remix_dictionary={1: [1]})
        user = user_tfm.build(input_file, user_file)
        user_transcript = model.transcribe(user_file, **options_dict)

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
                        "end": int(event["end"]) * 1000,
                        "channel": 1,
                    }
                )
            if i < len(agent_transcript["segments"]):
                event = agent_transcript["segments"][i]
                # push event to utterances list
                utterances.append(
                    {
                        "text": event["text"],
                        "start": event["start"] * 1000,
                        "end": event["end"] * 1000,
                        "channel": 2,
                    }
                )
        logger.critical(f"utterances: {utterances}")

        # time.sleep(5)
        logger.info(f"done {user_transcript}")
        finish(job=job, utterances=utterances)

        ackJob(delivery_tag=method.delivery_tag)
    except sox.core.SoxError as error:
        logger.error(f"sox error: {error}")
        alert.error(job["interaction_id"], error)


def transcribe(ch, method, properties, body):
    # dual_sox_thread = threading.Thread(
    #     target=test, args=(ch, method, properties, body)
    # )
    # dual_sox_thread.start()
    run_dual_sox(ch, method, properties, body)


def ackJob(delivery_tag):
    rabbit.consume_channel.basic_ack(delivery_tag)


def start():
    rabbit.consume(transcribe)


def finish(job, utterances):
    # connection = pika.BlockingConnection(
    #     pika.ConnectionParameters(
    #         host=rabbitmq_host,
    #         port=rabbitmq_port,
    #     )
    # )
    # channel = connection.channel()
    # channel.exchange_declare(
    #     exchange=rabbitmq_transcript_exchange,
    #     exchange_type="topic",
    #     durable=True,
    # )

    message = {
        "pattern": {"group": "analytics", "asr_processor": "whisper"},
        "data": {
            "transcription_job_id": job["transcription_job_id"],
            "base_path": job["base_path"],
            "audio_url": job["audio_url"],
            "asr_provider": job["asr_provider"],
            "asr_language": job["asr_language"],
            "sample_rate": job["sample_rate"],
            "num_samples": job["num_samples"],
            "channels": job["channels"],
            "audio_format": job["audio_format"],
            "is_silent": job["is_silent"],
            "status": "TRANSCRIPTION_FINISHED",
            "interaction_id": job["interaction_id"],
            "duration": job["duration"],
            "utterances": utterances,
            "pipeline": "default",
        },
    }

    markAsFinishedDto = {
        "transcription_job_id": job["transcription_job_id"],
        "utterances": utterances,
    }

    finished_url = f"{analytics_manager_url}/v3/transcript/job/finished"

    finished_post = requests.post(finished_url, json=markAsFinishedDto)
    rabbit.publish_finished(
        # exchange=rabbitmq_transcript_exchange,
        message=message,
        # message=json.dumps(message),
    )
    logger.info(
        f" {job['transcription_job_id']} {finished_post.status_code} marked as"
        " PROCESSED"
    )
