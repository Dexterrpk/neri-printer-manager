FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       python3-venv cups cups-client cups-filters ghostscript python3-cups \
       avahi-daemon avahi-utils policykit-1 samba smbclient \
       samba-common-bin libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 \
       libxcb-cursor0 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 \
       libxcb-keysyms1 libxcb-render-util0 \
    && rm -rf /var/lib/apt/lists/*
