FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       cups cups-client cups-browsed cups-filters ghostscript \
       avahi-daemon avahi-utils policykit-1 samba smbclient \
       libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*
