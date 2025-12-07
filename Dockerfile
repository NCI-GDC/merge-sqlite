ARG REGISTRY=docker.osdc.io/ncigdc
ARG BASE_CONTAINER_VERSION=latest

FROM ${REGISTRY}/python3.9-builder:latest as builder

ARG REGISTRY
ARG BASE_CONTAINER_VERSION


COPY ./ /merge_sqlite

WORKDIR /merge_sqlite

RUN pip install tox && tox -e build

FROM ${REGISTRY}/python3.9:latest

LABEL org.opencontainers.image.title="merge_sqlite" \
      org.opencontainers.image.description="Merge Sqllite files" \
      org.opencontainers.image.source="https://github.com/NCI-GDC/merge-sqlite" \
      org.opencontainers.image.vendor="NCI GDC"

COPY --from=builder /merge_sqlite/dist/*.whl /merge_sqlite/
COPY requirements.txt /merge_sqlite/

WORKDIR /merge_sqlite

RUN dnf install -y sqlite && \
    dnf clean all

RUN pip install --no-deps -r requirements.txt \
	&& pip install --no-deps *.whl \
	&& rm -f *.whl requirements.txt

USER app

#CMD ["merge_sqlite --help"]
#CMD ["merge_sqlite", "--help"]

# Correct CMD (split executable and args)
ENTRYPOINT ["merge_sqlite"]
CMD ["--help"]
