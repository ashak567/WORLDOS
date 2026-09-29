from datetime import UTC, datetime
import unittest

from app.fusion import can_auto_merge, normalized_name
from app.ingestion.natural_earth import parse_country_boundary
from app.ingestion.world_bank import parse_population
from app.main import natural_earth_bundle, world_bank_bundle


class WorldBankVerticalSliceTests(unittest.TestCase):
    def test_world_bank_record_becomes_evidence_backed_observation(self) -> None:
        payload = [{"page": 1}, [{
            "countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663,
        }]]
        record = parse_population(payload, "https://api.worldbank.org/example")[0]
        bundle = world_bank_bundle(record, None, datetime(2026, 9, 29, tzinfo=UTC))
        self.assertEqual(bundle.entity.source_key, "IND")
        self.assertEqual(bundle.observation.measure, "population.total")
        self.assertEqual(bundle.observation.value, 1428627663)
        self.assertTrue(bundle.evidence.content_hash)
        self.assertEqual(bundle.time_interval.starts_at.year, 2023)

    def test_fusion_refuses_name_only_auto_merge(self) -> None:
        self.assertEqual(normalized_name("Côte d'Ivoire"), "cote d ivoire")
        self.assertFalse(can_auto_merge(existing_source_key=None, incoming_source_key=None,
                                        existing_name="Congo", incoming_name="Congo"))
        self.assertTrue(can_auto_merge(existing_source_key="IND", incoming_source_key="IND",
                                       existing_name="India", incoming_name="Republic of India"))

    def test_natural_earth_polygon_uses_shared_iso_identifier(self) -> None:
        payload = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"ISO_A3": "IND", "NAME": "India"},
            "geometry": {"type": "Polygon", "coordinates": [[[68, 8], [97, 8], [68, 8]]]},
        }]}
        boundary = parse_country_boundary(payload, "IND", "https://example.test/natural-earth.geojson")
        bundle = natural_earth_bundle(boundary, datetime(2026, 9, 29, tzinfo=UTC))
        self.assertEqual(bundle.identifiers[0].scheme, "iso_3166_1_alpha_3")
        self.assertEqual(bundle.identifiers[0].value, "IND")
        self.assertEqual(bundle.geometry.geometry_kind, "country_boundary")

    def test_usgs_earthquake_feature_becomes_evidence_backed_event_and_bundle(self) -> None:
        from uuid import uuid4
        from app.ingestion.usgs import parse_earthquake_feature
        from app.main import usgs_earthquake_bundle

        feature = {
            "type": "Feature",
            "id": "us6000m0xm",
            "properties": {
                "mag": 6.2,
                "place": "8 km SW of Anamizu, Japan",
                "time": 1704093521584,
                "code": "6000m0xm",
                "title": "M 6.2 - 8 km SW of Anamizu, Japan",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [136.8272, 37.1895, 10.0],
            },
        }
        record = parse_earthquake_feature(feature, "https://earthquake.usgs.gov/test", "hash123")
        country_id = uuid4()
        bundle = usgs_earthquake_bundle(record, datetime(2026, 9, 29, tzinfo=UTC), containing_entity_id=country_id)
        self.assertEqual(bundle.entity.source_key, "us6000m0xm")
        self.assertEqual(bundle.identifiers[0].scheme, "usgs_event_id")
        self.assertEqual(bundle.identifiers[0].value, "us6000m0xm")
        self.assertEqual(bundle.observation.measure, "earthquake.magnitude")
        self.assertEqual(bundle.observation.value, 6.2)
        self.assertEqual(bundle.event.kind, "earthquake")
        self.assertEqual(bundle.geometry.geometry_kind, "epicenter")
        self.assertEqual(bundle.time_interval.precision, "instant")
        self.assertEqual(len(bundle.relationships), 1)
        self.assertEqual(bundle.relationships[0].predicate, "occurred_in")
        self.assertEqual(bundle.relationships[0].object_entity_id, country_id)
