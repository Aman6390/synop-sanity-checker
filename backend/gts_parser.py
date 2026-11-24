import re
from typing import Dict, List, Any, Optional

class GTSParser:
    """
    Parser for WMO GTS bulletins from AMSS Delhi (sendata.txt).
    Splits bulletins using standard WMO 'NNNN' terminators (and ZCZC headers),
    classifies message types, isolates AAXX blocks, enforces single-report per
    station per NNNN bulletin block, and records non-SYNOP activity.
    """

    NON_AAXX_CUTOFF = re.compile(
        r'\b(SX[A-Z]{2}\d{2}|TTAA|TTBB|TTCC|TTDD|PPAA|PPBB|PPCC|PPDD|SA[A-Z]{2}\d{2}|SP[A-Z]{2}\d{2}|US[A-Z]{2}\d{2}|UK[A-Z]{2}\d{2}|UL[A-Z]{2}\d{2}|UE[A-Z]{2}\d{2}|UG[A-Z]{2}\d{2}|UP[A-Z]{2}\d{2}|ZCZC)\b',
        re.IGNORECASE
    )

    @staticmethod
    def classify_bulletin_type(header: str, body: str) -> str:
        body_upper = body.upper()
        header_upper = header.upper()

        if "AAXX" in body_upper or header_upper.startswith(("SM", "SI", "SN")):
            return "SYNOP"
        elif any(k in body_upper for k in ["TTAA", "TTBB", "TTCC", "TTDD"]) or header_upper.startswith(("US", "UK", "UL", "UE")):
            return "TEMP"
        elif any(k in body_upper for k in ["PPAA", "PPBB", "PPCC", "PPDD"]) or header_upper.startswith(("UG", "UP")):
            return "PILOT"
        elif "METAR" in body_upper or header_upper.startswith("SA"):
            return "METAR"
        elif "SPECI" in body_upper or header_upper.startswith("SP"):
            return "SPECI"
        elif header_upper.startswith("SX") or "RH" in body_upper or "RF SINCE" in body_upper:
            return "REMARKS"
        return "OTHER"

    @classmethod
    def parse_bulletin_stream(cls, raw_text: str) -> Dict[str, Any]:
        """
        Parses full GTS bulletin stream by splitting on WMO 'NNNN' delimiters.
        Enforces intra-bulletin deduplication (max 1 report per station between NNNN).
        """
        # Split stream by NNNN
        raw_blocks = re.split(r'NNNN', raw_text)
        
        synops_by_station: Dict[str, List[Dict[str, Any]]] = {}
        activity_by_station: Dict[str, List[Dict[str, Any]]] = {}
        total_bulletins = 0

        for b_idx, block in enumerate(raw_blocks):
            b_text = block.strip()
            if not b_text:
                continue

            total_bulletins += 1

            # Extract sequence number if present (ZCZC xxx)
            m_seq = re.search(r'ZCZC\s+(\d+)', b_text)
            seq_num = m_seq.group(1) if m_seq else ""

            # Extract WMO header line: TTAAii CCCC YYGGgg [BBB]
            m_hdr = re.search(r'\b([A-Z]{4}\d{2})\s+([A-Z]{4})\s+(\d{6})(?:\s+([A-Z0-9]{3}))?', b_text)
            if m_hdr:
                bulletin_id = m_hdr.group(1)
                originating_center = m_hdr.group(2)
                header_timestamp = m_hdr.group(3)
                bbb = m_hdr.group(4) or ""
            else:
                # Fallback to splitting lines
                lines = [l.strip() for l in b_text.splitlines() if l.strip()]
                header_parts = lines[1].split() if len(lines) > 1 else []
                bulletin_id = header_parts[0] if len(header_parts) > 0 else ""
                originating_center = header_parts[1] if len(header_parts) > 1 else ""
                header_timestamp = header_parts[2] if len(header_parts) > 2 else ""
                bbb = header_parts[3] if len(header_parts) > 3 else ""

            is_correction = bool(bbb and re.match(r'^(COR|AMD|CC[A-Z])$', bbb, re.IGNORECASE))
            mtype = cls.classify_bulletin_type(bulletin_id, b_text)

            # Check if this bulletin block contains an AAXX surface synop section
            if "AAXX" in b_text:
                cls._extract_aaxx_reports(
                    b_text=b_text,
                    bulletin_id=bulletin_id,
                    seq_num=seq_num,
                    originating_center=originating_center,
                    header_timestamp=header_timestamp,
                    bbb=bbb,
                    is_correction=is_correction,
                    block_index=b_idx,
                    synops_by_station=synops_by_station,
                    activity_by_station=activity_by_station
                )
            else:
                # Non-AAXX message: scan for any 5-digit station code appearances
                cls._extract_non_aaxx_activities(
                    b_text=b_text,
                    bulletin_id=bulletin_id,
                    seq_num=seq_num,
                    originating_center=originating_center,
                    header_timestamp=header_timestamp,
                    mtype=mtype,
                    activity_by_station=activity_by_station
                )

        return {
            "synops_by_station": synops_by_station,
            "activity_by_station": activity_by_station,
            "total_bulletins": total_bulletins
        }

    @classmethod
    def _extract_aaxx_reports(
        cls,
        b_text: str,
        bulletin_id: str,
        seq_num: str,
        originating_center: str,
        header_timestamp: str,
        bbb: str,
        is_correction: bool,
        block_index: int,
        synops_by_station: Dict[str, List[Dict[str, Any]]],
        activity_by_station: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Isolates the AAXX section within the NNNN block, cuts off trailing non-AAXX sections,
        splits into reports, and strictly enforces max 1 report per station between NNNN.
        """
        aaxx_pos = b_text.find("AAXX")
        if aaxx_pos == -1:
            return

        aaxx_segment = b_text[aaxx_pos:]

        # Cut off any trailing non-AAXX bulletin that might appear before NNNN (e.g. SXIN remarks)
        m_cut = cls.NON_AAXX_CUTOFF.search(aaxx_segment[4:])
        if m_cut:
            trailing_snippet = aaxx_segment[4 + m_cut.start():]
            aaxx_segment = aaxx_segment[:4 + m_cut.start()]
            # Record the trailing snippet as non-AAXX activity if relevant
            cls._extract_non_aaxx_activities(
                b_text=trailing_snippet,
                bulletin_id=bulletin_id,
                seq_num=seq_num,
                originating_center=originating_center,
                header_timestamp=header_timestamp,
                mtype="REMARKS",
                activity_by_station=activity_by_station
            )

        # Extract observation day & hour from AAXX YYGGiw
        m_aaxx_hdr = re.search(r'AAXX\s+(\d{2})(\d{2})(\d)', aaxx_segment)
        if m_aaxx_hdr:
            obs_day = m_aaxx_hdr.group(1)
            obs_hour = m_aaxx_hdr.group(2) + "00"
            wind_ind = m_aaxx_hdr.group(3)
        else:
            obs_day = header_timestamp[:2] if len(header_timestamp) >= 2 else "00"
            obs_hour = header_timestamp[2:4] + "00" if len(header_timestamp) >= 4 else "0000"
            wind_ind = "4"

        # Split reports by '=' (WMO report terminator)
        raw_reports = aaxx_segment.split('=')

        # Intra-bulletin station map: strictly max 1 report per station in this NNNN block
        block_station_reports: Dict[str, str] = {}
        for rep in raw_reports:
            rep_clean = rep.strip()
            if not rep_clean:
                continue

            # Strip leading AAXX YYGGiw header if attached to the first report
            rep_clean = re.sub(r'^\s*AAXX\s+\d{5}\s*', '', rep_clean).strip()

            # Must contain a 5-digit station code (42xxx or 43xxx for IMD)
            stn_match = re.search(r'\b(4[23]\d{3})\b', rep_clean)
            if not stn_match:
                continue
            stn_id = stn_match.group(1)

            # Filter out non-synoptic remarks like 'RH 044%' or 'RF SINCE'
            if "RH " in rep_clean or "RF SINCE" in rep_clean:
                continue

            # Enforce single station occurrence per NNNN block
            if stn_id not in block_station_reports:
                block_station_reports[stn_id] = rep_clean + "="

        is_collective = len(block_station_reports) > 1

        for stn_id, rep_text in block_station_reports.items():
            report_item = {
                "station_id": stn_id,
                "observation_day": obs_day,
                "observation_hour": obs_hour,
                "wind_indicator": wind_ind,
                "raw_text": rep_text,
                "bulletin_id": bulletin_id,
                "seq_num": seq_num,
                "originating_center": originating_center,
                "header_timestamp": header_timestamp,
                "bbb": bbb,
                "is_correction": is_correction,
                "is_collective": is_collective,
                "block_index": block_index,
                "type": "SYNOP (Surface AAXX)"
            }

            if stn_id not in synops_by_station:
                synops_by_station[stn_id] = []
            synops_by_station[stn_id].append(report_item)

            # Record in activity log as well
            if stn_id not in activity_by_station:
                activity_by_station[stn_id] = []
            activity_by_station[stn_id].append({
                "station_id": stn_id,
                "timestamp": header_timestamp,
                "observation_hour": obs_hour,
                "type": "SYNOP (Surface AAXX)",
                "bulletin_id": bulletin_id,
                "seq_num": seq_num,
                "originating_center": originating_center,
                "raw_text": rep_text
            })

    @classmethod
    def _extract_non_aaxx_activities(
        cls,
        b_text: str,
        bulletin_id: str,
        seq_num: str,
        originating_center: str,
        header_timestamp: str,
        mtype: str,
        activity_by_station: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Scans for 5-digit station codes (42xxx / 43xxx) in non-AAXX reports
        and stores them into activity log.
        """
        station_matches = set(re.findall(r'\b(4[23]\d{3})\b', b_text))
        for station_id in station_matches:
            if station_id not in activity_by_station:
                activity_by_station[station_id] = []

            # Extract snippet of the line mentioning this station
            lines = [l.strip() for l in b_text.splitlines() if station_id in l]
            snippet = lines[0] if lines else b_text[:120].strip()

            activity_by_station[station_id].append({
                "station_id": station_id,
                "timestamp": header_timestamp,
                "observation_hour": header_timestamp[2:4] + "00" if len(header_timestamp) >= 4 else "0000",
                "type": mtype,
                "bulletin_id": bulletin_id,
                "seq_num": seq_num,
                "originating_center": originating_center,
                "raw_text": snippet
            })
