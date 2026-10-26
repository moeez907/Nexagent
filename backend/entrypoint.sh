#!/bin/bash
set -e

echo "🚀 Starting Virtual Framebuffer (Xvfb) on display :99..."
Xvfb :99 -screen 0 1280x800x24 -ac -nolisten tcp +extension GLX +extension RENDER &
export DISPLAY=:99
sleep 1

echo "🪟 Starting Openbox Window Manager..."
openbox &
sleep 0.5

echo "🖥️ Starting x11vnc server on port 5900..."
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -bg

echo "🌐 Starting noVNC Websockify bridge on 0.0.0.0:6080..."
websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 &
sleep 0.5

echo "⚡ Starting NexAgent FastAPI backend on port 8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
