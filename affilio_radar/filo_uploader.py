"""Filo video uploader for OfferChin's own short product videos.

This adapter uses Filo's authenticated upload page, not its native-republish API.
It deliberately distinguishes a public publication from an accepted submission
that is still awaiting review. Credentials are read only from the process env.
A push-triggered verification checks account access without publishing a video.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from offerchin_copy import normalize_brand_display_name
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

FILO_ORIGIN = "https://ifilo.net"
FILO_LOGIN_PATH = "/login?m=3&r=%2Fupload"
FILO_UPLOAD_PATH = "/upload"
FILO_MY_VIDEOS_PATH = "/my/videos"
FILO_PUBLISH_PATH = "/api/v1/video/publish"
FILO_PENDING_MARKERS = (
    "در صف انتشار",
    "در حال پردازش",
    "در انتظار تایید",
    "در انتظار تأیید",
    "ارسال شده برای اصلاح",
    "ارسال شده برای سانسور",
)
