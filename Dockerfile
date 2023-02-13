FROM python:3.10
RUN pip3 install aiohttp requests kubernetes
COPY SASI-PullAgent.py /SASI-PullAgent.py
COPY type /type
CMD python3 /SASI-PullAgent.py