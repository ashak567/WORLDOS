from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta, timezone

from app.ingestion.satellites import SatelliteRecord, satellite_to_api_state


class SatelliteApiStateTests(unittest.TestCase):
    def make_record(self, epoch: datetime, elements_epoch: datetime) -> SatelliteRecord:
        return SatelliteRecord(
            norad_id="12345",
            name="Test Satellite",
            designator="2020-001A",
            category="Test",
            operator="",
            launch_date="",
            apogee_km=500,
            perigee_km=480,
            inclination_deg=45,
            period_min=95,
            eccentricity=0.001,
            current_lat=10,
            current_lon=20,
            current_alt_km=490,
            current_velocity_kms=7.6,
            ground_track=[],
            epoch=epoch,
            elements_epoch=elements_epoch,
            elements_retrieved_at=epoch,
            feed_status="fresh",
        )

    def test_naive_element_epoch_is_treated_as_utc(self) -> None:
        record = self.make_record(
            datetime(2026, 10, 31, 12, tzinfo=UTC),
            datetime(2026, 10, 31, 10),
        )

        state = satellite_to_api_state(record)

        self.assertEqual(state["attributes"]["elements_age_hours"], 2)

    def test_aware_timestamps_with_different_offsets_are_compared_in_utc(self) -> None:
        record = self.make_record(
            datetime(2026, 10, 31, 14, tzinfo=timezone(timedelta(hours=2))),
            datetime(2026, 10, 6, 0, tzinfo=timezone(timedelta(hours=-4))),
        )

        state = satellite_to_api_state(record)

        self.assertEqual(state["attributes"]["elements_age_hours"], 608)


if __name__ == "__main__":
    unittest.main()
