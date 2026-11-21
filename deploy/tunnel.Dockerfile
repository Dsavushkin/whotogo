# SSH client that keeps a SOCKS proxy to a server abroad: the bot reaches Telegram through it.
FROM alpine:3.20
RUN apk add --no-cache openssh-client curl
