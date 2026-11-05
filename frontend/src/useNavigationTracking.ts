import { useState, useRef, useEffect, useCallback } from 'react';
import {
  RoadRouteResponse,
  UserNavigationState,
  computeDistanceMeters,
  computeBearingDegrees,
} from './api';

export function useNavigationTracking(activeRoadRoute: RoadRouteResponse | null) {
  const [navState, setNavState] = useState<UserNavigationState | null>(null);

  const animFrameRef = useRef<number | null>(null);
  const geoWatchIdRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);
  const simProgressRef = useRef<{
    segmentIndex: number;
    segmentFrac: number;
    speed_kmh: number;
  }>({
    segmentIndex: 0,
    segmentFrac: 0,
    speed_kmh: 50,
  });

  // Keep ref to activeRoadRoute to avoid stale closures in animation frame
  const routeRef = useRef<RoadRouteResponse | null>(activeRoadRoute);
  useEffect(() => {
    routeRef.current = activeRoadRoute;
  }, [activeRoadRoute]);

  // Clean up timers/listeners on unmount
  useEffect(() => {
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (geoWatchIdRef.current !== null) {
        navigator.geolocation.clearWatch(geoWatchIdRef.current);
      }
    };
  }, []);

  // Stop / Exit Navigation
  const stopNavigation = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (geoWatchIdRef.current !== null) {
      navigator.geolocation.clearWatch(geoWatchIdRef.current);
      geoWatchIdRef.current = null;
    }
    setNavState(null);
  }, []);

  // Set simulation speed
  const setSimSpeed = useCallback((speed: number) => {
    setNavState((prev) => (prev ? { ...prev, simulationSpeed: speed } : null));
  }, []);

  // Toggle Camera Follow
  const toggleCameraFollow = useCallback(() => {
    setNavState((prev) => (prev ? { ...prev, isCameraFollowing: !prev.isCameraFollowing } : null));
  }, []);

  // Recenter Camera
  const recenterCamera = useCallback(() => {
    setNavState((prev) => (prev ? { ...prev, isCameraFollowing: true } : null));
  }, []);

  // Simulation tick loop
  const runSimLoop = useCallback((timestamp: number) => {
    const route = routeRef.current;
    if (!route || route.polyline.length < 2) {
      return;
    }

    if (!lastTimeRef.current) {
      lastTimeRef.current = timestamp;
    }
    const dtSeconds = Math.min((timestamp - lastTimeRef.current) / 1000, 0.1);
    lastTimeRef.current = timestamp;

    setNavState((prev) => {
      if (!prev || !prev.isActive || !prev.isSimulating) {
        return prev;
      }

      if (prev.hasArrived) {
        return prev;
      }

      const { segmentIndex, segmentFrac, speed_kmh } = simProgressRef.current;
      const poly = route.polyline;
      const totalSegments = poly.length - 1;

      if (segmentIndex >= totalSegments) {
        return {
          ...prev,
          hasArrived: true,
          speed_kmh: 0,
          remainingDistance_m: 0,
          remainingDuration_s: 0,
          distanceToNextStep_m: 0,
          currentCoords: poly[poly.length - 1],
        };
      }

      const p1 = poly[segmentIndex];
      const p2 = poly[segmentIndex + 1];
      const segLengthM = Math.max(0.5, computeDistanceMeters(p1, p2));

      // Advance distance according to speed and simulation multiplier
      const moveDistanceM = (speed_kmh * 1000 / 3600) * dtSeconds * prev.simulationSpeed;
      let newFrac = segmentFrac + moveDistanceM / segLengthM;
      let newSegIndex = segmentIndex;

      while (newFrac >= 1.0 && newSegIndex < totalSegments - 1) {
        newFrac -= 1.0;
        newSegIndex += 1;
      }

      let hasArrived = false;
      if (newSegIndex >= totalSegments - 1 && newFrac >= 1.0) {
        newSegIndex = totalSegments - 1;
        newFrac = 1.0;
        hasArrived = true;
      }

      simProgressRef.current.segmentIndex = newSegIndex;
      simProgressRef.current.segmentFrac = newFrac;

      const curP1 = poly[newSegIndex];
      const curP2 = poly[Math.min(totalSegments, newSegIndex + 1)];

      const currentLon = curP1[0] + newFrac * (curP2[0] - curP1[0]);
      const currentLat = curP1[1] + newFrac * (curP2[1] - curP1[1]);
      const currentCoords: [number, number] = [currentLon, currentLat];

      const heading = computeBearingDegrees(curP1, curP2);

      // Maneuver step indexing: advance when within 30m of step waypoint
      let stepIdx = prev.currentStepIndex;
      const steps = route.steps;
      if (stepIdx < steps.length - 1) {
        const nextStepCoord = steps[stepIdx].coordinates;
        const distToStep = computeDistanceMeters(currentCoords, nextStepCoord);
        if (distToStep < 30) {
          stepIdx = Math.min(steps.length - 1, stepIdx + 1);
        }
      }

      // Distance to upcoming step
      const targetStepCoord = steps[stepIdx]?.coordinates || curP2;
      const distToNextStep = computeDistanceMeters(currentCoords, targetStepCoord);

      // Remaining distance along route polyline
      let remainingM = (1.0 - newFrac) * computeDistanceMeters(curP1, curP2);
      for (let i = newSegIndex + 1; i < totalSegments; i++) {
        remainingM += computeDistanceMeters(poly[i], poly[i + 1]);
      }

      const remainingDurationS = Math.round(
        remainingM / Math.max(1, (speed_kmh * 1000 / 3600))
      );

      return {
        ...prev,
        currentCoords,
        heading,
        speed_kmh: hasArrived ? 0 : speed_kmh,
        currentStepIndex: stepIdx,
        distanceToNextStep_m: Math.round(distToNextStep),
        remainingDistance_m: Math.round(remainingM),
        remainingDuration_s: remainingDurationS,
        hasArrived,
      };
    });

    animFrameRef.current = requestAnimationFrame(runSimLoop);
  }, []);

  // Start Navigation in either 'simulate' or 'gps' mode
  const startNavigation = useCallback(
    (mode: 'simulate' | 'gps' = 'simulate') => {
      const route = routeRef.current;
      if (!route || route.polyline.length < 2) {
        alert('Please calculate a road route first before starting navigation.');
        return;
      }

      // Clear any prior loop or watcher
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (geoWatchIdRef.current !== null) {
        navigator.geolocation.clearWatch(geoWatchIdRef.current);
        geoWatchIdRef.current = null;
      }

      const initialHeading = computeBearingDegrees(route.polyline[0], route.polyline[1]);
      const initialStepDist = computeDistanceMeters(
        route.polyline[0],
        route.steps[0]?.coordinates || route.polyline[1]
      );

      simProgressRef.current = {
        segmentIndex: 0,
        segmentFrac: 0,
        speed_kmh: 52, // realistic 52 km/h city cruising speed
      };
      lastTimeRef.current = 0;

      const initialNavState: UserNavigationState = {
        isActive: true,
        isSimulating: mode === 'simulate',
        simulationSpeed: 2, // 2x default for smooth responsive desktop viewing
        currentCoords: route.polyline[0],
        heading: initialHeading,
        speed_kmh: mode === 'simulate' ? 52 : 0,
        altitude_m: 12,
        currentStepIndex: 0,
        distanceToNextStep_m: Math.round(initialStepDist),
        remainingDistance_m: Math.round(route.total_distance_km * 1000),
        remainingDuration_s: Math.round(route.total_duration_min * 60),
        isCameraFollowing: true,
        hasArrived: false,
        accuracy_m: mode === 'gps' ? 15 : 20,
      };

      setNavState(initialNavState);

      if (mode === 'simulate') {
        animFrameRef.current = requestAnimationFrame(runSimLoop);
      } else {
        // Mode === 'gps'
        if (!navigator.geolocation) {
          alert('Geolocation is not supported by your browser. Falling back to simulated drive mode.');
          setNavState({ ...initialNavState, isSimulating: true });
          animFrameRef.current = requestAnimationFrame(runSimLoop);
          return;
        }

        let prevGpsCoords: [number, number] | null = null;
        let prevTimestamp = Date.now();

        const watchId = navigator.geolocation.watchPosition(
          (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            const accuracy = pos.coords.accuracy || 15;
            const now = Date.now();
            const currentCoords: [number, number] = [lon, lat];

            let heading = pos.coords.heading;
            if (heading === null || Number.isNaN(heading)) {
              if (prevGpsCoords) {
                heading = computeBearingDegrees(prevGpsCoords, currentCoords);
              } else {
                heading = initialHeading;
              }
            }

            let speedKmh = pos.coords.speed ? pos.coords.speed * 3.6 : 0;
            if (!pos.coords.speed && prevGpsCoords) {
              const distTraveledM = computeDistanceMeters(prevGpsCoords, currentCoords);
              const dtSec = (now - prevTimestamp) / 1000;
              if (dtSec > 0) {
                speedKmh = Math.min(130, (distTraveledM / dtSec) * 3.6);
              }
            }

            prevGpsCoords = currentCoords;
            prevTimestamp = now;

            // Match to closest step & compute remaining distance
            const steps = route.steps;
            let closestStepIdx = 0;
            let minDistToStep = Infinity;
            steps.forEach((s, idx) => {
              const d = computeDistanceMeters(currentCoords, s.coordinates);
              if (d < minDistToStep) {
                minDistToStep = d;
                closestStepIdx = idx;
              }
            });

            const distToDest = computeDistanceMeters(currentCoords, route.destination_coords);
            const hasArrived = distToDest < 35;

            setNavState((prevState) => {
              if (!prevState || !prevState.isActive) return prevState;
              return {
                ...prevState,
                currentCoords,
                heading: Math.round(heading || 0),
                speed_kmh: Math.round(speedKmh),
                accuracy_m: accuracy,
                currentStepIndex: closestStepIdx,
                distanceToNextStep_m: Math.round(minDistToStep),
                remainingDistance_m: Math.round(distToDest),
                remainingDuration_s: Math.round(
                  distToDest / Math.max(1, (speedKmh * 1000 / 3600) || 12)
                ),
                hasArrived,
              };
            });
          },
          (err) => {
            console.warn('Geolocation error during live navigation:', err);
          },
          {
            enableHighAccuracy: true,
            maximumAge: 1000,
            timeout: 15000,
          }
        );

        geoWatchIdRef.current = watchId;
      }
    },
    [runSimLoop]
  );

  // Switch between simulation and live GPS dynamically while running
  const toggleSimulate = useCallback(
    (simulate: boolean) => {
      startNavigation(simulate ? 'simulate' : 'gps');
    },
    [startNavigation]
  );

  // User panned camera away manually
  const onUserPannedCamera = useCallback(() => {
    setNavState((prev) => (prev ? { ...prev, isCameraFollowing: false } : null));
  }, []);

  return {
    navState,
    startNavigation,
    stopNavigation,
    setSimSpeed,
    toggleCameraFollow,
    recenterCamera,
    toggleSimulate,
    onUserPannedCamera,
  };
}
