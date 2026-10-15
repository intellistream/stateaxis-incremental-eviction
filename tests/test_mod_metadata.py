import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_owner_metadata_is_explicit() -> None:
    metadata = json.loads((ROOT / "MOD_METADATA.json").read_text())
    responsibility = metadata["responsibility"]
    assert responsibility["maintainers"] == [
        {
            "name": "Shuhao Zhang (Tony)",
            "github": "ShuhaoZhangTony",
        }
    ]
    assert responsibility["advisor_status"] == "none"
    assert responsibility["advisors"] == []
