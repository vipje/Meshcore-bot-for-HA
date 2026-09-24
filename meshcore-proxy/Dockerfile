ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages pyserial

COPY proxy.py /opt/proxy.py
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
