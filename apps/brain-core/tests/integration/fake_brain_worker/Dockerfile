FROM alpine:3.20
RUN apk add --no-cache bash git
COPY fake-claude.sh /usr/local/bin/fake-claude
RUN chmod +x /usr/local/bin/fake-claude
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/fake-claude"]
