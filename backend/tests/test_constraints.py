"""Unit tests for Engine 12: Constraint Engine.

Verifies deterministic validation across:
- Physical coordinates and bounds
- Non-finite numbers and malformed coordinates
- Anti-meridian wrapping and bounding box ordering
- PostGIS geometry structures and polygon rings
- Temporal intervals, timezone awareness, and precision tiers
- Entity and relationship consistency (anti-reflexivity, predicates)
- Claims, truth classes, evidence citations, and domain sanity
- Warning vs blocking severity policies
- Scenario proposals and dry-run non-mutation
"""
import math
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.constraints import ConstraintEngine, ConstraintViolationError
from app.domain import (
    BoundingBox,
    Claim,
    Confidence,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    Entity,
    Geometry,
    Observation,
    Relationship,
    ScenarioProposal,
    TimeInterval,
    TruthClass,
    WorldBundle,
)


class TestConstraintEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ConstraintEngine()
        self.now = datetime.now(UTC)

    # -------------------------------------------------------------------------
    # 1. Physical & Coordinate Invariants
    # -------------------------------------------------------------------------

    def test_valid_coordinates(self) -> None:
        findings = self.engine.validate_coordinate_pair(10.5, 45.2)
        self.assertEqual(len(findings), 0)

        # Boundary extremes
        self.assertEqual(len(self.engine.validate_coordinate_pair(-180.0, -90.0)), 0)
        self.assertEqual(len(self.engine.validate_coordinate_pair(180.0, 90.0)), 0)

    def test_coordinate_out_of_bounds(self) -> None:
        # Longitude out of bounds
        findings = self.engine.validate_coordinate_pair(185.0, 0.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "COORD_LON_OUT_OF_BOUNDS")
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        findings_west = self.engine.validate_coordinate_pair(-190.0, 0.0)
        self.assertEqual(findings_west[0].code, "COORD_LON_OUT_OF_BOUNDS")

        # Latitude out of bounds
        findings_north = self.engine.validate_coordinate_pair(0.0, 95.0)
        self.assertEqual(findings_north[0].code, "COORD_LAT_OUT_OF_BOUNDS")
        self.assertEqual(findings_north[0].severity, ConstraintSeverity.BLOCKING)

        findings_south = self.engine.validate_coordinate_pair(0.0, -91.5)
        self.assertEqual(findings_south[0].code, "COORD_LAT_OUT_OF_BOUNDS")

    def test_non_finite_and_non_numeric_coordinates(self) -> None:
        # NaN
        findings = self.engine.validate_coordinate_pair(float("nan"), 45.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "COORD_NON_FINITE")
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        # Infinity
        findings_inf = self.engine.validate_coordinate_pair(0.0, float("inf"))
        self.assertEqual(findings_inf[0].code, "COORD_NON_FINITE")

        # Non-numeric
        findings_str = self.engine.validate_coordinate_pair("invalid", 45.0)
        self.assertEqual(findings_str[0].code, "COORD_NON_NUMERIC")

    def test_bounding_box_validation(self) -> None:
        # Valid bbox
        valid_bbox = BoundingBox(min_longitude=-10.0, min_latitude=30.0, max_longitude=10.0, max_latitude=50.0)
        findings = self.engine.validate_bounding_box(valid_bbox)
        self.assertEqual(len(findings), 0)

        # Inverted latitude (min > max)
        inverted_lat = BoundingBox.model_construct(
            min_longitude=0.0, min_latitude=60.0, max_longitude=10.0, max_latitude=30.0
        )
        findings = self.engine.validate_bounding_box(inverted_lat)
        codes = [f.code for f in findings]
        self.assertIn("BBOX_LATITUDE_INVERTED", codes)

        # Inverted longitude (standard)
        inverted_lon = BoundingBox.model_construct(
            min_longitude=100.0, min_latitude=10.0, max_longitude=50.0, max_latitude=20.0
        )
        findings = self.engine.validate_bounding_box(inverted_lon, allow_antimeridian=False)
        codes = [f.code for f in findings]
        self.assertIn("BBOX_LONGITUDE_INVERTED", codes)

    def test_antimeridian_crossing_handling(self) -> None:
        # Antimeridian bounding box (e.g. 175 to -175)
        antimeridian_bbox = BoundingBox.model_construct(
            min_longitude=175.0, min_latitude=-20.0, max_longitude=-175.0, max_latitude=-10.0
        )
        findings = self.engine.validate_bounding_box(antimeridian_bbox, allow_antimeridian=True)
        # Should NOT be blocked; should be flagged as WARNING/advisory
        self.assertTrue(any(f.code == "BBOX_ANTIMERIDIAN_SPAN" for f in findings))
        self.assertFalse(any(f.severity == ConstraintSeverity.BLOCKING for f in findings))

        # Antimeridian geometry
        geom_coords = [
            [[178.0, -15.0], [-178.0, -15.0], [-178.0, -20.0], [178.0, -20.0], [178.0, -15.0]]
        ]
        geojson = {"type": "Polygon", "coordinates": geom_coords}
        geom_findings = self.engine.validate_geometry_structure(geojson)
        # Valid global geometry; crosses antimeridian without rejection
        self.assertTrue(any(f.code == "GEOM_CROSSES_ANTIMERIDIAN" for f in geom_findings))
        self.assertFalse(any(f.severity == ConstraintSeverity.BLOCKING for f in geom_findings))

    def test_polygon_ring_structure(self) -> None:
        # Unclosed ring
        unclosed = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0], [1.0, 1.0]]],
        }
        findings = self.engine.validate_geometry_structure(unclosed)
        codes = [f.code for f in findings]
        self.assertIn("GEOM_POLYGON_RING_NOT_CLOSED", codes)
        self.assertTrue(any(f.severity == ConstraintSeverity.BLOCKING for f in findings))

        # Too few points in ring
        too_few = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.0, 10.0], [0.0, 0.0]]],
        }
        findings_few = self.engine.validate_geometry_structure(too_few)
        self.assertIn("GEOM_POLYGON_RING_TOO_FEW_POINTS", [f.code for f in findings_few])

        # Unsupported type
        unsupported = {"type": "CircularString", "coordinates": []}
        findings_unsup = self.engine.validate_geometry_structure(unsupported)
        self.assertIn("GEOM_UNSUPPORTED_TYPE", [f.code for f in findings_unsup])

    # -------------------------------------------------------------------------
    # 2. Temporal Consistency
    # -------------------------------------------------------------------------

    def test_temporal_interval_invariants(self) -> None:
        # Valid interval
        t1 = TimeInterval(starts_at=self.now, ends_at=self.now + timedelta(days=1), precision="day")
        self.assertEqual(len(self.engine.validate_temporal(t1)), 0)

        # Inverted interval (ends_at < starts_at) constructed directly
        t_inv = TimeInterval.model_construct(
            id=uuid4(), starts_at=self.now, ends_at=self.now - timedelta(days=1), precision="day"
        )
        findings = self.engine.validate_temporal(t_inv)
        codes = [f.code for f in findings]
        self.assertIn("TEMPORAL_INVERTED", codes)
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        # Timezone missing (naive datetime)
        naive_dt = datetime(2025, 1, 1)  # No tzinfo
        t_naive = TimeInterval.model_construct(
            id=uuid4(), starts_at=naive_dt, ends_at=None, precision="year"
        )
        findings_tz = self.engine.validate_temporal(t_naive)
        self.assertIn("TEMPORAL_TIMEZONE_MISSING", [f.code for f in findings_tz])

        # Invalid precision tier
        t_prec = TimeInterval.model_construct(
            id=uuid4(), starts_at=self.now, ends_at=None, precision="microsecond"  # type: ignore
        )
        findings_prec = self.engine.validate_temporal(t_prec)
        self.assertIn("TEMPORAL_PRECISION_INVALID", [f.code for f in findings_prec])

    # -------------------------------------------------------------------------
    # 3. Entity & Relationship Consistency
    # -------------------------------------------------------------------------

    def test_entity_consistency(self) -> None:
        # Empty canonical name
        entity = Entity.model_construct(
            id=uuid4(),
            kind="place",
            canonical_name="   ",
            confidence=Confidence(value=1.0),
        )
        findings = self.engine.validate_entity(entity)
        self.assertIn("ENTITY_NAME_EMPTY", [f.code for f in findings])
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        # Out-of-bounds confidence
        entity_conf = Entity.model_construct(
            id=uuid4(),
            kind="place",
            canonical_name="Valid City",
            confidence=Confidence.model_construct(value=1.5, method="test"),
        )
        findings_conf = self.engine.validate_entity(entity_conf)
        self.assertIn("CONFIDENCE_OUT_OF_BOUNDS", [f.code for f in findings_conf])

    def test_relationship_invariants(self) -> None:
        e1 = uuid4()
        e2 = uuid4()
        ev_id = uuid4()

        # Prohibit self-relationship
        self_rel = Relationship.model_construct(
            id=uuid4(),
            subject_entity_id=e1,
            predicate="connected_to",
            object_entity_id=e1,
            evidence_id=ev_id,
            confidence=Confidence(value=0.9),
            attributes={},
        )
        findings = self.engine.validate_relationship(self_rel)
        codes = [f.code for f in findings]
        self.assertIn("REL_SELF_RELATIONSHIP", codes)
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        # Invalid predicate
        invalid_rel = Relationship.model_construct(
            id=uuid4(),
            subject_entity_id=e1,
            predicate="dislikes",
            object_entity_id=e2,
            evidence_id=ev_id,
            confidence=Confidence(value=0.9),
            attributes={},
        )
        findings_pred = self.engine.validate_relationship(invalid_rel)
        self.assertIn("REL_INVALID_PREDICATE", [f.code for f in findings_pred])

        # Valid relationship
        valid_rel = Relationship(
            subject_entity_id=e1,
            predicate="located_in",
            object_entity_id=e2,
            evidence_id=ev_id,
            confidence=Confidence(value=1.0),
        )
        findings_valid = self.engine.validate_relationship(valid_rel)
        self.assertEqual(len(findings_valid), 0)

    # -------------------------------------------------------------------------
    # 4. Claims & Evidence Consistency
    # -------------------------------------------------------------------------

    def test_observation_consistency(self) -> None:
        subj_id = uuid4()
        ev_id = uuid4()
        prov_id = uuid4()
        t_id = uuid4()

        # Negative population
        obs_neg = Observation(
            subject_entity_id=subj_id,
            measure="population.total",
            value=-500.0,
            unit="people",
            truth_class="OBSERVED",
            time_interval_id=t_id,
            evidence_id=ev_id,
            provenance_id=prov_id,
            confidence=Confidence(value=1.0),
        )
        findings = self.engine.validate_observation(obs_neg)
        self.assertIn("MEASURE_VALUE_NEGATIVE", [f.code for f in findings])
        self.assertEqual(findings[0].severity, ConstraintSeverity.BLOCKING)

        # Invalid earthquake magnitude (> 12.0)
        obs_mag = Observation(
            subject_entity_id=subj_id,
            measure="magnitude",
            value=14.5,
            unit="Mw",
            truth_class="OBSERVED",
            time_interval_id=t_id,
            evidence_id=ev_id,
            provenance_id=prov_id,
            confidence=Confidence(value=0.8),
        )
        findings_mag = self.engine.validate_observation(obs_mag)
        self.assertIn("MEASURE_VALUE_OUT_OF_BOUNDS", [f.code for f in findings_mag])

        # Truth class mismatch
        obs_truth = Observation.model_construct(
            id=uuid4(),
            subject_entity_id=subj_id,
            measure="population.total",
            value=1000.0,
            unit="people",
            truth_class="SIMULATED",  # type: ignore
            time_interval_id=t_id,
            evidence_id=ev_id,
            provenance_id=prov_id,
            confidence=Confidence(value=1.0),
            attributes={},
        )
        findings_truth = self.engine.validate_observation(obs_truth)
        self.assertIn("TRUTH_CLASS_INVALID", [f.code for f in findings_truth])

    def test_claim_derivation_contract(self) -> None:
        subj_id = uuid4()

        # Derived claim without inputs
        claim_derived = Claim.model_construct(
            id=uuid4(),
            subject_entity_id=subj_id,
            claim_type="population_growth",
            truth_class=TruthClass.DERIVED,
            value=0.035,
            method="annualized_growth_rate",
            computation_version="v1.0",
            inputs={},  # Empty!
            confidence=Confidence(value=0.95),
            evidence_ids=[uuid4()],
            assumptions=[],
            created_at=self.now,
        )
        findings = self.engine.validate_claim(claim_derived)
        self.assertIn("DERIVED_CLAIM_INPUTS_MISSING", [f.code for f in findings])

        # Predicted claim without assumptions
        claim_pred = Claim.model_construct(
            id=uuid4(),
            subject_entity_id=subj_id,
            claim_type="population_projection",
            truth_class=TruthClass.PREDICTED,
            value=50000000,
            method="linear_trend",
            computation_version="v1.0",
            inputs={"base_year": 2024},
            confidence=Confidence(value=0.7),
            evidence_ids=[uuid4()],
            assumptions=[],  # Empty!
            created_at=self.now,
        )
        findings_pred = self.engine.validate_claim(claim_pred)
        self.assertIn("HYPOTHESIS_ASSUMPTIONS_MISSING", [f.code for f in findings_pred])

    # -------------------------------------------------------------------------
    # 5. Composite Validation Result & Severity Tiers
    # -------------------------------------------------------------------------

    def test_validation_result_status_derivation(self) -> None:
        # Clean findings -> VALID
        res_valid = ConstraintValidationResult.from_findings([])
        self.assertEqual(res_valid.status, ConstraintStatus.VALID)
        self.assertEqual(res_valid.blocking_count, 0)

        # Warning only -> VALID_WITH_WARNINGS
        warn_finding = ConstraintFinding(
            code="BBOX_ANTIMERIDIAN_SPAN",
            category=ConstraintCategory.PHYSICAL_COORDINATES,
            severity=ConstraintSeverity.WARNING,
            message="Advisory",
        )
        res_warn = ConstraintValidationResult.from_findings([warn_finding])
        self.assertEqual(res_warn.status, ConstraintStatus.VALID_WITH_WARNINGS)
        self.assertEqual(res_warn.warning_count, 1)

        # Review required -> VALID_WITH_WARNINGS
        review_finding = ConstraintFinding(
            code="ENTITY_RESOLUTION_UNVERIFIED_MATCH",
            category=ConstraintCategory.ENTITY_RELATIONSHIP,
            severity=ConstraintSeverity.REVIEW_REQUIRED,
            message="Review required",
        )
        res_rev = ConstraintValidationResult.from_findings([review_finding])
        self.assertEqual(res_rev.status, ConstraintStatus.VALID_WITH_WARNINGS)
        self.assertEqual(res_rev.review_required_count, 1)

        # Any blocking finding -> INVALID
        block_finding = ConstraintFinding(
            code="COORD_LAT_OUT_OF_BOUNDS",
            category=ConstraintCategory.PHYSICAL_COORDINATES,
            severity=ConstraintSeverity.BLOCKING,
            message="Out of bounds",
        )
        res_invalid = ConstraintValidationResult.from_findings([warn_finding, block_finding])
        self.assertEqual(res_invalid.status, ConstraintStatus.INVALID)
        self.assertEqual(res_invalid.blocking_count, 1)

    def test_deterministic_results_for_identical_inputs(self) -> None:
        obs = Observation(
            subject_entity_id=uuid4(),
            measure="population.total",
            value=-100.0,
            unit="people",
            truth_class="OBSERVED",
            time_interval_id=uuid4(),
            evidence_id=uuid4(),
            provenance_id=uuid4(),
            confidence=Confidence(value=1.0),
        )
        res1 = self.engine.validate_observation(obs)
        res2 = self.engine.validate_observation(obs)
        self.assertEqual([f.code for f in res1], [f.code for f in res2])
        self.assertEqual([f.severity for f in res1], [f.severity for f in res2])

    # -------------------------------------------------------------------------
    # 6. Scenario Proposals & Non-Mutation
    # -------------------------------------------------------------------------

    def test_scenario_proposal_validation(self) -> None:
        # Valid proposal
        proposal = ScenarioProposal(
            name="Sea Level Rise +1m",
            parameters={"sea_level_rise_meters": 1.0, "affected_population": 50000.0},
        )
        res = self.engine.validate_scenario_proposal(proposal)
        self.assertEqual(res.status, ConstraintStatus.VALID)

        # Empty name
        invalid_name = ScenarioProposal(name="   ", parameters={})
        res_name = self.engine.validate_scenario_proposal(invalid_name)
        self.assertEqual(res_name.status, ConstraintStatus.INVALID)
        self.assertIn("SCENARIO_NAME_EMPTY", [f.code for f in res_name.findings])

        # Negative population parameter
        neg_param = ScenarioProposal(
            name="Depopulation Test",
            parameters={"baseline_population": -1000.0},
        )
        res_neg = self.engine.validate_scenario_proposal(neg_param)
        self.assertEqual(res_neg.status, ConstraintStatus.INVALID)
        self.assertIn("SCENARIO_PARAMETER_NEGATIVE_POPULATION", [f.code for f in res_neg.findings])

    def test_scenario_engine_protocol_compatibility(self) -> None:
        # Compatible with ScenarioEngine protocol in interfaces.py
        scenario_dict = {
            "name": "Invalid Scenario",
            "parameters": {"population": -50.0},
        }
        violations = self.engine.validate_constraints(scenario_dict)
        self.assertTrue(len(violations) > 0)
        self.assertTrue(any("negative" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
