FROM alpine:3.22.2

RUN apk update && apk add --no-cache \
    ttyd \
    bash \
    nano \
    curl \
    git \
    vim \
    wget

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser


CMD ["ttyd", "-p", "7681", "--interface", "0.0.0.0", "--writable", "--client-option", "logLevel=DEBUG", "bash"]

