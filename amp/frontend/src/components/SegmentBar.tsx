import { useEffect, useState, useCallback, useRef } from "react";
import { api, type SegmentStatus } from "../api";

interface SegmentBarProps {
  songId: string;
  durationMs: number;
}

export function SegmentBar({ songId, durationMs }: SegmentBarProps) {
  const [segments, setSegments] = useState<SegmentStatus[]>([]);
  const inFlightRef = useRef(false); // P12: in-flight guard

  const fetchSegments = useCallback(async () => {
    // P12: Guard against overlapping polls
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const data = await api.getSegmentStatuses(songId);
      setSegments(data.segments);
    } catch {
      // Silently fail — segment bar is non-critical
    } finally {
      inFlightRef.current = false;
    }
  }, [songId]);

  // Poll every 500ms (P12: with in-flight guard)
  useEffect(() => {
    fetchSegments();
    const timer = setInterval(fetchSegments, 500);
    return () => clearInterval(timer);
  }, [fetchSegments]);

  // Click-to-seek: map click position to time
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!durationMs || segments.length === 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      const targetMs = Math.floor(ratio * durationMs);
      // Notify backend of seek
      api.seek(targetMs).catch(() => {});
      // Also update the audio element
      const audio = document.querySelector("audio");
      if (audio) {
        audio.currentTime = targetMs / 1000;
      }
    },
    [durationMs, segments.length],
  );

  if (segments.length === 0) return null;

  return (
    <div className="segment-bar" onClick={handleClick} title="Click to seek">
      {segments.map((seg) => (
        <div
          key={seg.index}
          className={`segment-cell ${seg.status}`}
          title={`Segment ${seg.index === -1 ? "init" : seg.index}: ${seg.status}`}
        />
      ))}
    </div>
  );
}
