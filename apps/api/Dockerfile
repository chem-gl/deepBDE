FROM pytorch/pytorch:2.3.0-cuda11.8-cudnn8-runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        latexmk && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/
COPY deepbde/requirements.txt /app/deepbde/
RUN pip install --upgrade pip && \
    pip install -r deepbde/requirements.txt && \
    pip cache purge && \
    pip install -r requirements.txt


COPY . /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000

RUN pip install dgl==1.1.2 -f https://data.dgl.ai/wheels/torch-2.3/repo.html

ENTRYPOINT ["/entrypoint.sh"]
