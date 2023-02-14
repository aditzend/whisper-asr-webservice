import pika
import json

connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host="192.168.43.170",
        port="30072",
    )
)

channel = connection.channel()

channel.exchange_declare(exchange="asr", exchange_type="topic", durable=True)

routing_key = "transcribe.short.whisper.cpu"

# message = {
#     "pattern": {"group": "SHORT_DURATION", "processor": "CPU"},
#     "data": {
#         "asr_language": "es",
#         "audio_url": (
#             "/Users/alexander/Downloads/calls/210614222408193_ACD_00001.mp3"
#         ),
#         "duration": 11520,
#         "sample_rate": 8000,
#         "channels": 2,
#         "audio_format": "mp3",
#     },
# }


message = {
    "pattern": {"group": "SHORT_DURATION", "processor": "CPU"},
    "data": {
        "transcription_id": "210614222408193_ACD_00001_TJ_202301191514",
        "interaction_id": "210614222408193_ACD_00001",
        "audio_format": "mp3",
        "sample_rate": 8000,
        "base_path": "/Users/alexander/Downloads/calls",
        "language": "es",
        "duration": 11520,
        "channels": 2,
    },
}
i = 0
while i < 2:
    i += 1
    message["data"][
        "transcription_id"
    ] = f"{'210614222408193_ACD_00001_TJ_202301191514'}---{i}"  # [:-1
    channel.basic_publish(
        exchange="asr", routing_key=routing_key, body=json.dumps(message)
    )
    print(f"{i} sent")

connection.close()
