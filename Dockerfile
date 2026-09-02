FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid agent --create-home --shell /usr/sbin/nologin agent

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=agent:agent . ./
RUN mkdir -p /data/sessions /workspace \
    && chown -R agent:agent /data /workspace

USER agent

EXPOSE 8765

CMD ["python", "-m", "agent.web", "--host", "0.0.0.0", "--port", "8765", "--session-dir", "/data/sessions"]
