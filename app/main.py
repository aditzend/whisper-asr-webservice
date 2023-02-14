import logging
import coloredlogs
from dotenv import load_dotenv
import transcribe

# import transcribe


load_dotenv()

FORMAT = (
    "[WHISPER] - %(asctime)s %(levelname)7s %(module)-20s "
    "%(threadName)-10s %(message)s "
)


# logging.Formatter(FORMAT, "%m/%d/%Y, %H:%M:%S ")
logging.basicConfig(level=logging.INFO, format=FORMAT)
coloredlogs.install(level="INFO", fmt=FORMAT)
logger = logging.getLogger("main")


def test_callback(ch, method, properties, body):
    logger.info(" [x] Received %r" % body)


logger.info("Starting Whisper Worker ")

transcribe.start()

# host = os.getenv("RABBITMQ_HOST") or ""
# port = os.getenv("RABBITMQ_PORT") or ""
# transcript_exchange = os.getenv("RABBITMQ_TRANSCRIPT_EXCHANGE") or ""
# all_finished_exchange = os.getenv("RABBITMQ_ALL_FINISHED_EXCHANGE") or ""
# whisper_transcription_queue = os.getenv("RABBITMQ_WHISPER_JOBS_QUEUE") or ""
# all_finished_queue = os.getenv("RABBITMQ_ALL_FINISHED_QUEUE") or ""
# whisper_transcription_routing_key = os.getenv("RABBITMQ_WHISPER_JOBS_ROUTING_KEY") or ""

# consumer = rabbit.Consumer(
#     host=host,
#     port=port,
#     exchange=transcript_exchange,
#     queue=whisper_transcription_queue,
#     routing_key=whisper_transcription_routing_key,
# )
# consumer.run()
# transcribe.consume()
