ARG REGISTRY=docker.osdc.io/ncigdc
ARG BASE_CONTAINER_VERSION=latest

FROM ${REGISTRY}/python3.9-builder:${BASE_CONTAINER_VERSION} as builder

COPY ./ /merge_sqlite

WORKDIR /merge_sqlite

RUN pip install tox && tox -e build

FROM ${REGISTRY}/python3.9:${BASE_CONTAINER_VERSION}

LABEL org.opencontainers.image.title="merge_sqlite" \
      org.opencontainers.image.description="Merge Sqllite files" \
      org.opencontainers.image.source="https://github.com/NCI-GDC/merge-sqlite" \
      org.opencontainers.image.vendor="NCI GDC"

COPY --from=builder /merge_sqlite/dist/*.whl /merge_sqlite/
COPY requirements.txt /merge_sqlite/

WORKDIR /merge_sqlite

RUN pip install --no-deps -r requirements.txt \
	&& pip install --no-deps *.whl \
	&& rm -f *.whl requirements.txt

USER app

CMD ["merge_sqlite --help"]
