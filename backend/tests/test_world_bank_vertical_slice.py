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

    def test_observation_refuses_non_observed_truth_class(self) -> None:
        from uuid import uuid4
        from pydantic import ValidationError
        from app.domain import Confidence, Observation

        # 1. Observation defaults to OBSERVED
        obs = Observation(
            subject_entity_id=uuid4(),
            measure="test.measure",
            value=42.0,
            unit="units",
            time_interval_id=uuid4(),
            evidence_id=uuid4(),
            provenance_id=uuid4(),
            confidence=Confidence(value=1.0),
        )
        self.assertEqual(obs.truth_class, "OBSERVED")

        # 2. Observation strictly rejects any non-OBSERVED truth_class
        with self.assertRaises(ValidationError):
            Observation(
                subject_entity_id=uuid4(),
                measure="test.derived",
                value=42.0,
                unit="units",
                truth_class="DERIVED",  # type: ignore[arg-type]
                time_interval_id=uuid4(),
                evidence_id=uuid4(),
                provenance_id=uuid4(),
                confidence=Confidence(value=1.0),
            )

        with self.assertRaises(ValidationError):
            Observation(
                subject_entity_id=uuid4(),
                measure="test.predicted",
                value=42.0,
                unit="units",
                truth_class="PREDICTED",  # type: ignore[arg-type]
                time_interval_id=uuid4(),
                evidence_id=uuid4(),
                provenance_id=uuid4(),
                confidence=Confidence(value=1.0),
            )

    def test_claim_derivation_contract_enforcement(self) -> None:
        from uuid import uuid4
        from pydantic import ValidationError
        from app.domain import Claim, Confidence, TruthClass

        entity_id = uuid4()
        ev_id = uuid4()

        # 1. DERIVED claim must preserve inputs and method
        with self.assertRaises(ValidationError):
            Claim(
                subject_entity_id=entity_id,
                claim_type="growth_rate",
                truth_class=TruthClass.DERIVED,
                value=12.5,
                method="rate_calc_v1",
                computation_version="v1",
                inputs={},  # Empty inputs must fail validation!
                confidence=Confidence(value=0.9),
            )

        # 2. PREDICTED claim must document explicit assumptions
        with self.assertRaises(ValidationError):
            Claim(
                subject_entity_id=entity_id,
                claim_type="projected_gdp",
                truth_class=TruthClass.PREDICTED,
                value=500.0,
                method="arima_forecast_v1",
                computation_version="v1",
                assumptions=[],  # Missing assumptions must fail!
                confidence=Confidence(value=0.6),
            )

        # 3. Valid DERIVED claim succeeds and preserves full derivation lineage
        valid_claim = Claim(
            subject_entity_id=entity_id,
            claim_type="growth_rate",
            truth_class=TruthClass.DERIVED,
            value={"percentage": 5.4},
            unit="percent",
            method="two_point_pct_v1",
            computation_version="worldos-v1",
            inputs={"obs_1": "100", "obs_2": "105.4"},
            evidence_ids=[ev_id],
            confidence=Confidence(value=0.95),
        )
        self.assertEqual(valid_claim.truth_class, TruthClass.DERIVED)
        self.assertEqual(valid_claim.evidence_ids, [ev_id])
        self.assertEqual(valid_claim.method, "two_point_pct_v1")

    def test_relationship_distinct_entities_validation(self) -> None:
        from uuid import uuid4
        from pydantic import ValidationError
        from app.domain import Confidence, Relationship

        e1 = uuid4()
        ev_id = uuid4()
        # Valid distinct entities
        rel = Relationship(
            subject_entity_id=e1,
            predicate="located_in",
            object_entity_id=uuid4(),
            evidence_id=ev_id,
            confidence=Confidence(value=1.0),
        )
        self.assertEqual(rel.predicate, "located_in")

        # Refuses self-referential relationship
        with self.assertRaises(ValidationError):
            Relationship(
                subject_entity_id=e1,
                predicate="located_in",
                object_entity_id=e1,
                evidence_id=ev_id,
                confidence=Confidence(value=1.0),
            )

    def test_bounding_box_validation(self) -> None:
        from pydantic import ValidationError
        from app.domain import BoundingBox

        # Valid bounding box
        bbox = BoundingBox(
            min_longitude=68.0,
            min_latitude=8.0,
            max_longitude=97.0,
            max_latitude=35.0,
        )
        self.assertEqual(bbox.min_longitude, 68.0)
        self.assertEqual(bbox.max_latitude, 35.0)

        # Inverted longitude (min > max)
        with self.assertRaises(ValidationError):
            BoundingBox(
                min_longitude=100.0,
                min_latitude=10.0,
                max_longitude=50.0,
                max_latitude=20.0,
            )

        # Inverted latitude (min > max)
        with self.assertRaises(ValidationError):
            BoundingBox(
                min_longitude=10.0,
                min_latitude=50.0,
                max_longitude=20.0,
                max_latitude=10.0,
            )

        # Coordinate out of range
        with self.assertRaises(ValidationError):
            BoundingBox(
                min_longitude=-190.0,
                min_latitude=0.0,
                max_longitude=0.0,
                max_latitude=0.0,
            )

    def test_temporal_scope_and_world_context_models(self) -> None:
        from datetime import UTC, datetime
        from uuid import uuid4
        from pydantic import ValidationError
        from app.domain import (
            BoundingBox,
            ContextQueryScope,
            EvidenceCitation,
            SpatialScope,
            TemporalScope,
            WorldContext,
        )

        t1 = datetime(2023, 1, 1, tzinfo=UTC)
        t2 = datetime(2023, 12, 31, tzinfo=UTC)

        # Valid temporal scope
        ts = TemporalScope(starts_at=t1, ends_at=t2, precision="year")
        self.assertEqual(ts.precision, "year")

        # Invalid interval (starts_at > ends_at)
        with self.assertRaises(ValidationError):
            TemporalScope(starts_at=t2, ends_at=t1)

        # Valid WorldContext assembly
        bbox = BoundingBox(min_longitude=0.0, min_latitude=0.0, max_longitude=10.0, max_latitude=10.0)
        scope = ContextQueryScope(
            spatial=SpatialScope(bounding_box=bbox, filter_type="intersects"),
            temporal=ts,
            limit=50,
        )
        ev_id = uuid4()
        citation = EvidenceCitation(
            evidence_id=ev_id,
            source_id=uuid4(),
            source_slug="test-source",
            source_name="Test Source",
            locator="https://example.test/evidence",
            retrieved_at=t1,
        )
        ctx = WorldContext(
            query_scope=scope,
            entities=[{"id": str(uuid4()), "canonical_name": "Test Entity"}],
            evidence=[citation],
            assumptions_or_limitations=["Bounded by test bbox"],
        )
        self.assertEqual(len(ctx.entities), 1)
        self.assertEqual(len(ctx.evidence), 1)
        self.assertEqual(ctx.evidence[0].evidence_id, ev_id)
        self.assertEqual(ctx.query_scope.spatial.bounding_box.max_longitude, 10.0)


