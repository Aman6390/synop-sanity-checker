import ssl
import urllib.request
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("AMSSFetcher")
AMSS_URL = "https://amssdelhi.gov.in/sendata/sendata.txt"

class AMSSFetcher:
    def __init__(self):
        self.last_raw_text: str = ""
        self.last_fetch_time: Optional[datetime] = None
        self.last_fetch_status: str = "IDLE"
        self.last_fetch_error: Optional[str] = None
        self.total_bytes: int = 0

    def fetch_live_data(self) -> str:
        """
        Fetches live bulletin stream from amssdelhi.gov.in using legacy DH/SSL cipher compatibility.
        """
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # Vital for AMSS Delhi server compatibility
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/plain, */*"
        }
        req = urllib.request.Request(AMSS_URL, headers=headers)

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                self.last_raw_text = content
                self.last_fetch_time = datetime.now(timezone.utc)
                self.last_fetch_status = "SUCCESS"
                self.last_fetch_error = None
                self.total_bytes = len(content)
                logger.info(f"Fetched {len(content)} bytes from AMSS Delhi.")
                return content
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to fetch from AMSS Delhi: {err_msg}")
            self.last_fetch_status = "ERROR"
            self.last_fetch_error = err_msg
            if self.last_raw_text:
                logger.info("Using cached raw data.")
                return self.last_raw_text
            raise RuntimeError(f"Unable to fetch live data from AMSS Delhi: {err_msg}")
