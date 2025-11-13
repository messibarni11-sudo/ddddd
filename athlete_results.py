"""Lekéri és kiírja egy magyar atléta eddig publikált eredményeit az Atletika.hu oldalról.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urljoin
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.atletika.hu"
SEARCH_URL = f"{BASE_URL}/kereses"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0 Safari/537.36"
)

MONTHS = {
    "januar": 1,
    "január": 1,
    "februar": 2,
    "február": 2,
    "marcius": 3,
    "március": 3,
    "aprilis": 4,
    "április": 4,
    "majus": 5,
    "május": 5,
    "junius": 6,
    "június": 6,
    "julius": 7,
    "július": 7,
    "augusztus": 8,
    "szeptember": 9,
    "oktober": 10,
    "október": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class ResultRow:
    date_value: Optional[date]
    date_text: str
    columns: Dict[str, str]
    date_header: str

    def formatted(self) -> str:
        formatted_date = (
            self.date_value.isoformat() if self.date_value else self.date_text
        )
        other_parts = []
        for header, value in self.columns.items():
            if header == self.date_header or not value:
                continue
            other_parts.append(f"{header}: {value}")
        details = " | ".join(other_parts) if other_parts else "Nincs további adat"
        return f"{formatted_date} | {details}"


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def parse_date(text: str) -> Optional[date]:
    cleaned = text.strip()
    if not cleaned:
        return None

    numeric_match = re.search(r"(\d{4})[.\-\/]\s*(\d{1,2})[.\-\/]\s*(\d{1,2})", cleaned)
    if numeric_match:
        year, month, day = map(int, numeric_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    month_match = re.search(
        r"(\d{4})\.\s*([a-záéíóöőúüű]+)\s+(\d{1,2})",
        cleaned.lower(),
    )
    if month_match:
        year = int(month_match.group(1))
        month_name = month_match.group(2)
        day = int(month_match.group(3))
        month = MONTHS.get(month_name)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def request_html(url: str, params: Optional[dict] = None) -> BeautifulSoup:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "hu"},
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def find_athlete_profile(name: str) -> Optional[str]:
    soup = request_html(SEARCH_URL, params={"search_api_fulltext": name})
    normalized_target = normalize_text(name)

    for anchor in soup.select("a"):
        href = anchor.get("href")
        if not href:
            continue
        text = anchor.get_text(strip=True)
        if not text:
            continue
        normalized_text = normalize_text(text)
        if "/versenyzok/" in href and normalized_target in normalized_text:
            return urljoin(BASE_URL, href)
    # fallback: first athlete link
    for anchor in soup.select("a"):
        href = anchor.get("href")
        if href and "/versenyzok/" in href:
            return urljoin(BASE_URL, href)
    return None


def extract_results(profile_url: str) -> List[ResultRow]:
    soup = request_html(profile_url)
    results: List[ResultRow] = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if not headers:
            continue
        date_indices = [idx for idx, header in enumerate(headers) if "dátum" in header.lower()]
        if not date_indices:
            continue
        date_idx = date_indices[0]
        body = table.find("tbody") or table
        for row in body.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if len(cells) != len(headers):
                continue
            columns = dict(zip(headers, cells))
            date_text = cells[date_idx]
            results.append(
                ResultRow(
                    date_value=parse_date(date_text),
                    date_text=date_text,
                    columns=columns,
                    date_header=headers[date_idx],
                )
            )
    return results


def main() -> int:
    try:
        name = input("add meg egy magyar atlétának a nevét! ").strip()
    except EOFError:
        return 1

    if not name:
        print("Nem adtál meg nevet.")
        return 1

    try:
        profile_url = find_athlete_profile(name)
    except requests.RequestException as exc:
        print("Nem sikerült elérni az Atletika.hu oldalát:", exc)
        return 1

    if not profile_url:
        print("Nem találtam a megadott névhez tartozó versenyzői profilt.")
        return 1

    try:
        results = extract_results(profile_url)
    except requests.RequestException as exc:
        print("Nem sikerült letölteni az eredményeket:", exc)
        return 1

    if not results:
        print("Nem találtam közzétett eredményeket ezen a profilon.")
        return 0

    results.sort(key=lambda row: row.date_value or date.min)
    for row in results:
        print(row.formatted())
    return 0


if __name__ == "__main__":
    sys.exit(main())
