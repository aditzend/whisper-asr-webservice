import pika
import logging
import os
from dotenv import load_dotenv

load_dotenv()


class PubSub:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.host = os.getenv("RABBITMQ_HOST") or ""
        self.port = os.getenv("RABBITMQ_PORT") or 0
        self.transcription_finished_exchange = (
            os.getenv("RABBITMQ_TRANSCRIPTION_FINISHED_EXCHANGE") or ""
        )
        self.transcription_finished_routing_key = (
            os.getenv("RABBITMQ_TRANSCRIPTION_FINISHED_ROUTING_KEY") or ""
        )
        self.whisper_jobs_exchange = (
            os.getenv("RABBITMQ_WHISPER_JOBS_EXCHANGE") or ""
        )

        self.whisper_jobs_queue = (
            os.getenv("RABBITMQ_WHISPER_JOBS_QUEUE") or ""
        )
        self.whisper_jobs_routing_key = (
            os.getenv("RABBITMQ_WHISPER_JOBS_ROUTING_KEY") or ""
        )

        self.publish_connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                client_properties={
                    "connection_name": "transcription-finished-connection"
                },
            )
        )
        self.consume_connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                client_properties={
                    "connection_name": "whisper-jobs-connection"
                },
            )
        )

    def publish_finished(self, message):
        try:
            channel = self.publish_connection.channel()
            channel.exchange_declare(
                self.transcription_finished_exchange,
                exchange_type="topic",
                durable=True,
            )

            channel.basic_publish(
                exchange=self.transcription_finished_exchange,
                routing_key=self.transcription_finished_routing_key,
                body=message,
            )
            self.logger.info(
                f"Published message to {self.transcription_finished_exchange}"
            )
            self.publish_connection.close()

        except IOError as error:
            self.logger.error(f"Error publishing message: {error}")
            raise

    def consume(self, callback):
        try:
            self.consume_channel = self.consume_connection.channel()

            self.consume_channel.exchange_declare(
                exchange=self.whisper_jobs_exchange,
                exchange_type="topic",
                durable=True,
            )

            result = self.consume_channel.queue_declare(
                queue=self.whisper_jobs_queue, exclusive=False, durable=True
            )

            queue_name = result.method.queue

            self.consume_channel.queue_bind(
                exchange=self.whisper_jobs_exchange,
                queue=queue_name,
                routing_key=self.whisper_jobs_routing_key,
            )
            self.logger.info(f"Waiting for transcription jobs on {queue_name}")
            self.consume_channel.basic_consume(
                queue=self.whisper_jobs_queue,
                on_message_callback=callback,
                auto_ack=False,
            )

            self.consume_channel.start_consuming()

        except IOError as error:
            self.logger.error(f"Error: {error}")
            raise
