FROM python:3.9.9-slim


RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get -qq update \
    && apt-get -qq install --no-install-recommends \
    ffmpeg \
    sox \
    libsox-fmt-mp3 \
    && rm -rf /var/lib/apt/lists/*


# ARG TARGETPLATFORM
# RUN if [ "$TARGETPLATFORM" = "linux/amd64" ]; pip3 install torch==1.13.0 -f https://download.pytorch.org/whl/cpu; fi;
# RUN if [ "$TARGETPLATFORM" = "linux/arm64" ]; pip3 install torch==1.13.0; fi;



RUN pip3 install torch==1.13.0 -f https://download.pytorch.org/whl/cpu;

RUN pip3 install openai-whisper
RUN pip3 install sox
RUN pip3 install numpy
RUN pip3 install python-dotenv
RUN pip3 install requests
RUN pip3 install coloredlogs
RUN pip3 install pika


COPY /app /app

CMD ["python3", "app/main.py" ]