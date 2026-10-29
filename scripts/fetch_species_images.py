"""Find a freely licensed photo for every platform species on Wikimedia Commons.

For each species the English Wikipedia article (by scientific name, then common name) supplies its
lead image, or failing that the first Commons photo whose file name contains the exact scientific name; Wikimedia Commons supplies the image's licence, author and a 480 px thumbnail. Only
public-domain, CC0, CC BY and CC BY-SA images are kept, and an article reached through a redirect
to a different taxon (for example a genus page) is rejected so a photo of another species is never
used. Images are linked, not copied; the credit for each is stored with it and shown on the site.

Writes data/processed/species_images.json. Usage: python scripts/fetch_species_images.py
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from pathlib import Path

import psycopg
import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "processed" / "species_images.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "BioIndia/1.0 (MSc biodiversity research platform; https://github.com/deepaksharma0801/bioindia)"}
FREE_LICENCE = re.compile(r"^(public domain|pd\b|cc0|cc[- ]by(-sa)?[- ]\d)", re.IGNORECASE)
BATCH = 40


def call(url: str, **params) -> dict:
    params.update(action="query", format="json", formatversion=2)
    for attempt in range(5):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        except requests.ConnectionError:
            time.sleep(5 * (attempt + 1))  # Wikimedia occasionally drops connections; back off and retry
            continue
        if response.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Wikimedia API did not answer after retries: {url}")


def plain(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def lead_images(titles: list[str]) -> dict[str, tuple[str, str]]:
    """Map each requested title to (article title, lead image file name), rejecting cross-taxon redirects."""
    found: dict[str, tuple[str, str]] = {}
    for start in range(0, len(titles), BATCH):
        chunk = titles[start:start + BATCH]
        data = call(WIKIPEDIA, titles="|".join(chunk), prop="pageimages", piprop="name", redirects=1)
        query = data.get("query", {})
        redirect = {r["from"]: r["to"] for r in query.get("redirects", [])}
        normal = {n["from"]: n["to"] for n in query.get("normalized", [])}
        pages = {p["title"]: p for p in query.get("pages", []) if not p.get("missing")}
        for title in chunk:
            normalised = normal.get(title, title)
            target = redirect.get(normalised, normalised)
            page = pages.get(target)
            if not page or "pageimage" not in page:
                continue
            # A scientific name redirecting to a one-word title is a genus or family page: wrong species.
            if target != normalised and len(target.split()) == 1:
                continue
            found[title] = (target, page["pageimage"].replace("_", " "))
        time.sleep(0.5)
    return found


def commons_search(scientific: str) -> str | None:
    """First Commons photo whose file name contains the exact scientific name (fallback when the article has no image)."""
    data = call(COMMONS, list="search", srnamespace=6, srlimit=10, srsearch=f'intitle:"{scientific}" filetype:bitmap')
    for hit in data.get("query", {}).get("search", []):
        title = hit["title"].removeprefix("File:")
        if re.search(r"locali[sz]ation|map|distribution|range|herbarium sheet", title, re.IGNORECASE):
            continue  # maps and range plots are not photos of the species
        if scientific.lower() in title.lower() and re.search(r"\.(jpe?g|png|webp)$", title, re.IGNORECASE):
            return title
    return None


def commons_info(files: list[str]) -> dict[str, dict]:
    info: dict[str, dict] = {}
    for start in range(0, len(files), BATCH):
        chunk = files[start:start + BATCH]
        data = call(COMMONS, titles="|".join("File:" + f for f in chunk), prop="imageinfo",
                    iiprop="url|extmetadata|mime", iiurlwidth=480)
        for page in data.get("query", {}).get("pages", []):
            if page.get("missing") or not page.get("imageinfo"):
                continue  # not on Commons (e.g. a non-free English Wikipedia upload)
            ii = page["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            licence = plain(meta.get("LicenseShortName", {}).get("value"))
            if not FREE_LICENCE.match(licence) or not ii.get("mime", "").startswith("image/") or ii.get("mime") == "image/svg+xml":
                continue
            info[page["title"].removeprefix("File:")] = {
                "thumb": ii.get("thumburl") or ii.get("url"),
                "page": ii.get("descriptionurl"),
                "artist": plain(meta.get("Artist", {}).get("value"))[:120] or "Unknown author",
                "licence": licence,
                "licence_url": plain(meta.get("LicenseUrl", {}).get("value")) or None,
            }
        time.sleep(0.5)
    return info


def main() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        species = connection.execute("SELECT species_id, scientific_name, common_name FROM species ORDER BY species_id").fetchall()

    by_scientific = lead_images([s[1] for s in species])
    missing = [s for s in species if s[1] not in by_scientific and s[2]]
    by_common = lead_images([s[2] for s in missing])
    chosen: dict[str, tuple[str, str, str]] = {}
    for species_id, scientific, common in species:
        hit = by_scientific.get(scientific) or (by_common.get(common) if common else None)
        if hit:
            chosen[species_id] = (hit[0], hit[1], "scientific name" if scientific in by_scientific else "common name")

    for species_id, scientific, _ in species:
        if species_id not in chosen:
            file = commons_search(scientific)
            if file:
                chosen[species_id] = (scientific, file, "Commons file name")
            time.sleep(0.3)

    files = sorted({file for _, file, _ in chosen.values()})
    info = commons_info(files)
    images = {}
    for species_id, (article, file, matched_by) in sorted(chosen.items()):
        if file in info:
            article_url = None if matched_by == "Commons file name" else f"https://en.wikipedia.org/wiki/{article.replace(' ', '_')}"
            images[species_id] = {**info[file], "file": file, "article": article_url, "matched_by": matched_by}

    OUTPUT.write_text(json.dumps({
        "source": "Wikimedia Commons, via the lead image of each species' English Wikipedia article",
        "licence_rule": "public domain, CC0, CC BY or CC BY-SA only; credit shown with each image",
        "retrieved": time.strftime("%Y-%m-%d"),
        "images": images,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(images)} of {len(species)} species have a freely licensed photo "
          f"({len(chosen) - len(images)} lead images were not free or not on Commons; {len(species) - len(chosen)} had no article image).")


if __name__ == "__main__":
    main()
