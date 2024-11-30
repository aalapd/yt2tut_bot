#!/bin/bash
# entrypoint.sh

# Start WARP
warp-svc &
sleep 5

# Register and connect WARP
warp-cli --accept-tos register
warp-cli enable-always-on
warp-cli connect

# Start SOCKS proxy
danted

# Keep container running
tail -f /dev/null