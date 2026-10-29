"""真实联网验收：python -m scripts.smoke_live；不使用任何模拟记录。"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from scholar.service import search_papers
from scholar.processing import export_csv, filter_papers


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = {"api_key": os.getenv("OPENALEX_API_KEY", ""), "email": os.getenv("CROSSREF_MAILTO", "")}
    result = search_papers("polysilazane corrosion coating", limit=25, **config)
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "query": "polysilazane corrosion coating",
              **asdict(result)}
    (output / "live-search.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "live-search.csv").write_bytes(export_csv(result.papers))
    print("Source counts:", result.counts)
    print("Errors:", result.errors)
    print("Merged:", len(result.papers))
    assert result.papers, "No live papers received"
    for p in result.papers[:3]:
        print(p.title, p.year, p.doi, p.url, sep=" | ")
    selected = next(p for p in result.papers if p.doi)
    lookup = search_papers(selected.doi, doi_mode=True, **config)
    assert any(p.doi == selected.doi for p in lookup.papers), "DOI lookup failed"
    print("DOI lookup:", lookup.counts, lookup.errors)
    filtered = filter_papers(result.papers, journal=selected.journal)
    assert selected in filtered
    print("Local journal filter and CSV export: PASS")
    if result.errors or lookup.errors:
        raise SystemExit("Partial success: see source errors above")
    print("Both live sources and DOI lookup: PASS")


if __name__ == "__main__":
    main()
