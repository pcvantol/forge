# Brongebonden roadmapinventarissen

Deze map bewaart gedateerde analytische snapshots. Zij is geen tweede backlog, uitvoerbare DAG, planningservice of peer-statusautoriteit. Voor het hoogoverbeeld en de autonomie-eerst focus: [Roadmapoverzicht](../ROADMAP_OVERVIEW_AND_AUTONOMY_FOCUS.md).

## 17 september 2026

[2026-09-17.json](2026-09-17.json) bewaart de volledige oorspronkelijke telling: 194 unieke benoemde records, 165 analytische rollup-eenheden, waarvan 7 gedeelde nodes, en 34 mogelijke aftrapfamilies. De oorspronkelijke bronrevisies, statussen, telregels, families, recordvolgorde en samenvoegredenen zijn behouden. Dit is een compacte representatie, geen hertelling of code-/runtime-audit.

De oorspronkelijke invoerbestanden waren `roadmap_inventory.md` en `roadmap_inventory.json`; hun SHA-256 staat in `source_artifact_sha256`. De JSON is voor repositoryopslag genormaliseerd om identieke bronmetadata niet 194 maal te herhalen. Alle oorspronkelijke itemvelden zijn verliesvrij terug te construeren en zijn bij vastlegging programmatisch met het aangeleverde origineel vergeleken. De originele chatbestanden hoeven niet beschikbaar te zijn om deze repositorysnapshot te lezen.

## Formaat `roadmap-inventory.compact/v1`

- `source_pins`: exacte commit per repository.
- `sources`: repository, relatief bronpad en historische chat-citatiereference. De laatste is alleen retained metadata, geen bruikbare repositoryautoriteit. De stabiele bronlink volgt uit repository, commit en pad.
- `groups`: een rij met meerdere IDs waarvoor dezelfde metadata geldt. Ontbrekende waarden volgen uit `defaults`; een expliciete status overschrijft de default.
- `normalization_rules`: de oorspronkelijke analytische redenen en `rolled_up_into`-IDs; dit is geen claim dat alle scopes één-op-één equivalent zijn.
- `original_order`: oorspronkelijke volgorde van de 194 records.
- `summary`, `counting_rules` en `family_counts`: ongewijzigde uitkomsten en beperkingen van de aangeleverde analyse.

Een `PLANNED` in deze snapshot is het documentaire label op de genoemde bronpin, niet het oordeel dat vandaag alles nog ongebouwd is. De niet-optelbare deelnametotalen zijn geen unieke backlogtelling. De 34 families zijn geen minimum of garantie voor het aantal prompts.

## Reproduceren zonder netwerk of productruntime

Vanaf de repository-root kan de onderstaande read-only standaardbibliotheekcode de records uitpakken en de interne telling toetsen. Dit kwalificeert de inventarisstructuur, niet de owning productimplementaties of hun huidige roadmapstatus.

```python
import collections
import json
from pathlib import Path

snapshot = json.loads(Path("docs/roadmap/inventory/2026-09-17.json").read_text(encoding="utf-8"))
items = {}
for group in snapshot["groups"]:
    source = snapshot["sources"][group["source"]]
    repository = source["repository"]
    commit = snapshot["source_pins"][repository.rsplit("/", 1)[-1]]
    rule = snapshot["normalization_rules"].get(
        group.get("normalization_rule"), {"reason": None, "rolled_up_into": []}
    )
    for item_id in group["ids"]:
        assert item_id not in items, ("duplicate ID", item_id)
        items[item_id] = {
            "id": item_id,
            "owners": group["owners"],
            "family": group["family"],
            "documentary_status": group.get("documentary_status", "PLANNED"),
            "counted_in_rollup": group.get("counted_in_rollup", True),
            "normalization_reason": rule["reason"],
            "rolled_up_into": rule["rolled_up_into"],
            "source_repository": repository,
            "source_commit": commit,
            "source_path": source["path"],
            "source_url": f"https://github.com/{repository}/blob/{commit}/{source['path']}",
            "citation_ref": source["legacy_chat_citation_ref"],
        }
assert len(snapshot["original_order"]) == len(set(snapshot["original_order"])) == len(items)
assert set(snapshot["original_order"]) == set(items)
ordered = [items[item_id] for item_id in snapshot["original_order"]]
counted = [item for item in ordered if item["counted_in_rollup"]]
summary = snapshot["summary"]
assert len(ordered) == summary["raw_named_records_in_selected_scoped_inventory"] == 194
assert len(counted) == summary["rollup_planning_units"] == 165
assert len(ordered) - len(counted) == summary["collapsed_overlap_records"] == 29
assert sum(len(item["owners"]) > 1 for item in counted) == summary["shared_unique_units"] == 7
exclusive = collections.Counter(item["owners"][0] for item in counted if len(item["owners"]) == 1)
assert dict(exclusive) == summary["exclusive_units_by_repository"]
for repository, families in snapshot["family_counts"].items():
    observed = collections.Counter(
        item["family"] for item in counted if item["owners"] == [repository]
    )
    assert dict(observed) == families
assert sum(len(families) for families in snapshot["family_counts"].values()) == 34
print("Inventory structure PASS: 194 records / 165 rollup units / 34 families")
```

Een volgende inventaris krijgt een nieuwe gedateerde snapshot en een verklaarde delta. Verander deze historische bronlabels niet in live voortgang; werk actuele bewijsstatus bij in de owning administratie.
