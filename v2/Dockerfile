FROM python:3.10
RUN pip3 install aiohttp requests kubernetes prometheus_api_client
COPY SASI-PullAgent.py /SASI-PullAgent.py
COPY type /root/type
CMD python3 /SASI-PullAgent.py