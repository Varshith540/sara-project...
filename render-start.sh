#!/usr/bin/env bash

# Self-Healing Gunicorn Start Script for Render Free Tier
# This ensures workers are recycled frequently to prevent memory leaks

exec gunicorn resumexpert.wsgi:application \
    --workers 1 \
    --max-requests 10 \
    --max-requests-jitter 5 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
